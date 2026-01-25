# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>
import os

from flask import render_template, request, redirect, flash, url_for, abort
from flask_babel import lazy_gettext, gettext
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField, FileField
from wtforms.fields.simple import TextAreaField
from wtforms.validators import InputRequired, Length, Optional
from wtforms_sqlalchemy.fields import QuerySelectField

from app.logic.releases import do_create_vcs_release, LogicError, do_create_zip_release
from app.models import Package, db, User, PackageState, Permission, UserRank, PackageDailyStats, LuantiRelease, \
	PackageRelease, PackageUpdateTrigger, PackageUpdateConfig, ReleaseState
from app.rediscache import has_key, set_temp_key, make_download_key
from app.tasks.importtasks import check_update_config
from app.utils.models import is_package_page
from app.utils.flask import is_user_bot
from app.utils.misc import nonempty_or_none, normalize_line_endings
from . import bp, get_package_tabs


@bp.route("/packages/<author>/<name>/releases/", methods=["GET", "POST"])
@is_package_page
def list_releases(package):
	return render_template("packages/releases_list.html",
			package=package,
			tabs=get_package_tabs(current_user, package), current_tab="releases")


def get_mt_releases(is_max):
	query = LuantiRelease.query.order_by(db.asc(LuantiRelease.id))
	if is_max:
		query = query.limit(query.count() - 1)
	else:
		query = query.filter(LuantiRelease.name != "0.4.17")

	return query


class CreatePackageReleaseForm(FlaskForm):
	name        = StringField(lazy_gettext("Name"), [InputRequired(), Length(1, 30)])
	title       = StringField(lazy_gettext("Title"), [Optional(), Length(1, 100)], filters=[nonempty_or_none])
	release_notes = TextAreaField(lazy_gettext("Release Notes"), [Optional(), Length(1, 5000)],
			filters=[nonempty_or_none, normalize_line_endings])
	upload_mode = RadioField(lazy_gettext("Method"), choices=[("upload", lazy_gettext("File Upload"))], default="upload")
	vcs_label   = StringField(lazy_gettext("Git reference (ie: commit hash, branch, or tag)"), default=None)
	file_upload = FileField(lazy_gettext("File Upload"))
	min_rel     = QuerySelectField(lazy_gettext("Minimum Luanti Version"), [InputRequired()],
			query_factory=lambda: get_mt_releases(False), get_pk=lambda a: a.id, get_label=lambda a: a.name)
	max_rel     = QuerySelectField(lazy_gettext("Maximum Luanti Version"), [InputRequired()],
			query_factory=lambda: get_mt_releases(True), get_pk=lambda a: a.id, get_label=lambda a: a.name)
	submit      = SubmitField(lazy_gettext("Save"))


class EditPackageReleaseForm(FlaskForm):
	name     = StringField(lazy_gettext("Name"), [InputRequired(), Length(1, 30)])
	title    = StringField(lazy_gettext("Title"), [InputRequired(), Length(1, 100)], filters=[nonempty_or_none])
	release_notes = TextAreaField(lazy_gettext("Release Notes"), [Optional(), Length(1, 5000)],
			filters=[nonempty_or_none, normalize_line_endings])
	url      = StringField(lazy_gettext("URL"), [Optional()])
	task_id  = StringField(lazy_gettext("Task ID"), filters = [lambda x: x or None])
	approved = BooleanField(lazy_gettext("Is Approved"))
	min_rel  = QuerySelectField(lazy_gettext("Minimum Luanti Version"), [InputRequired()],
			query_factory=lambda: get_mt_releases(False), get_pk=lambda a: a.id, get_label=lambda a: a.name)
	max_rel  = QuerySelectField(lazy_gettext("Maximum Luanti Version"), [InputRequired()],
			query_factory=lambda: get_mt_releases(True), get_pk=lambda a: a.id, get_label=lambda a: a.name)
	submit   = SubmitField(lazy_gettext("Save"))


@bp.route("/packages/<author>/<name>/releases/new/", methods=["GET", "POST"])
@login_required
@is_package_page
def create_release(package):
	if current_user.email is None and not current_user.rank.at_least(UserRank.ADMIN):
		flash(gettext("You must add an email address to your account and confirm it before you can manage packages"), "danger")
		return redirect(url_for("users.email_notifications"))

	if not package.check_perm(current_user, Permission.MAKE_RELEASE):
		return redirect(package.get_url("packages.view"))

	# Initial form class from post data and default data
	form = CreatePackageReleaseForm()
	if package.repo is not None:
		form.upload_mode.choices = [("vcs", gettext("Import from Git")), ("upload", gettext("Upload .zip file"))]
		if request.method == "GET":
			form.upload_mode.data = "vcs"
			form.vcs_label.data = request.args.get("ref")

	if request.method == "GET":
		form.title.data = request.args.get("title")

	if form.validate_on_submit():
		try:
			if form.upload_mode.data == "vcs":
				rel = do_create_vcs_release(current_user, package, form.name.data, form.title.data, form.release_notes.data,
						form.vcs_label.data, form.min_rel.data.get_actual(), form.max_rel.data.get_actual())
			else:
				rel = do_create_zip_release(current_user, package, form.name.data, form.title.data, form.release_notes.data,
						form.file_upload.data, form.min_rel.data.get_actual(), form.max_rel.data.get_actual())
			return redirect(url_for("tasks.check", id=rel.task_id, r=rel.get_edit_url()))
		except LogicError as e:
			flash(e.message, "danger")

	return render_template("packages/release_new.html", package=package, form=form)


@bp.route("/packages/<author>/<name>/releases/<int:id>/download/")
@is_package_page
def download_release(package, id):
	release = PackageRelease.query.get(id)
	if release is None or release.package != package:
		abort(404)

	ip = request.headers.get("X-Forwarded-For") or request.remote_addr
	if ip is not None and not is_user_bot():
		user_agent = request.headers.get("User-Agent") or ""
		is_luanti = user_agent.startswith("Luanti") or user_agent.startswith("Minetest")
		reason = request.args.get("reason")
		PackageDailyStats.update(package, is_luanti, reason)

		key = make_download_key(ip, release.package)
		if not has_key(key):
			set_temp_key(key, "true")

			bonus = 0
			if reason == "new":
				bonus = 1
			elif reason == "dependency" or reason == "update":
				bonus = 0.5

			PackageRelease.query.filter_by(id=release.id).update({
					"downloads": PackageRelease.downloads + 1
				})

			Package.query.filter_by(id=package.id).update({
					"downloads": Package.downloads + 1,
					"score_downloads": Package.score_downloads + bonus,
					"score": Package.score + bonus
				})

		db.session.commit()

	return redirect(release.url)


@bp.route("/packages/<author>/<name>/releases/<int:id>/")
@is_package_page
def view_release(package, id):
	release: PackageRelease = PackageRelease.query.get(id)
	if release is None or release.package != package:
		abort(404)

	return render_template("packages/release_view.html", package=package, release=release)


@bp.route("/packages/<author>/<name>/releases/<int:id>/edit/", methods=["GET", "POST"])
@login_required
@is_package_page
def edit_release(package, id):
	release: PackageRelease = PackageRelease.query.get(id)
	if release is None or release.package != package:
		abort(404)

	canEdit	= package.check_perm(current_user, Permission.MAKE_RELEASE)
	canApprove = release.check_perm(current_user, Permission.APPROVE_RELEASE)
	if not (canEdit or canApprove):
		return redirect(package.get_url("packages.view"))

	# Initial form class from post data and default data
	form = EditPackageReleaseForm(formdata=request.form, obj=release)

	if request.method == "GET":
		# HACK: fix bug in wtforms
		form.approved.data = release.approved

	if form.validate_on_submit():
		if canEdit:
			release.name = form.name.data
			release.title = form.title.data
			release.release_notes = form.release_notes.data
			release.min_rel = form.min_rel.data.get_actual()
			release.max_rel = form.max_rel.data.get_actual()

		if package.check_perm(current_user, Permission.CHANGE_RELEASE_URL):
			release.url = form.url.data
			release.task_id = form.task_id.data
			if release.task_id is not None:
				release.task_id = None

		if canApprove:
			if form.approved.data:
				release.approve(current_user)
			else:
				release.state = ReleaseState.UNAPPROVED

		db.session.commit()
		return redirect(package.get_url("packages.list_releases"))

	return render_template("packages/release_edit.html", package=package, release=release, form=form)



class BulkReleaseForm(FlaskForm):
	set_min = BooleanField(lazy_gettext("Set Min"))
	min_rel  = QuerySelectField(lazy_gettext("Minimum Luanti Version"), [InputRequired()],
			query_factory=lambda: get_mt_releases(False), get_pk=lambda a: a.id, get_label=lambda a: a.name)
	set_max = BooleanField(lazy_gettext("Set Max"))
	max_rel  = QuerySelectField(lazy_gettext("Maximum Luanti Version"), [InputRequired()],
			query_factory=lambda: get_mt_releases(True), get_pk=lambda a: a.id, get_label=lambda a: a.name)
	only_change_none = BooleanField(lazy_gettext("Only change values previously set as none"))
	submit   = SubmitField(lazy_gettext("Update"))


@bp.route("/packages/<author>/<name>/releases/bulk_change/", methods=["GET", "POST"])
@login_required
@is_package_page
def bulk_change_release(package):
	if not package.check_perm(current_user, Permission.MAKE_RELEASE):
		return redirect(package.get_url("packages.view"))

	# Initial form class from post data and default data
	form = BulkReleaseForm()

	if request.method == "GET":
		form.only_change_none.data = True
	elif form.validate_on_submit():
		only_change_none = form.only_change_none.data

		for release in package.releases.all():
			if form.set_min.data and (not only_change_none or release.min_rel is None):
				release.min_rel = form.min_rel.data.get_actual()
			if form.set_max.data and (not only_change_none or release.max_rel is None):
				release.max_rel = form.max_rel.data.get_actual()

		db.session.commit()

		return redirect(package.get_url("packages.list_releases"))

	return render_template("packages/release_bulk_change.html", package=package, form=form)


@bp.route("/packages/<author>/<name>/releases/<int:id>/delete/", methods=["POST"])
@login_required
@is_package_page
def delete_release(package, id):
	release = PackageRelease.query.get(id)
	if release is None or release.package != package:
		abort(404)

	if not release.check_perm(current_user, Permission.DELETE_RELEASE):
		return redirect(package.get_url("packages.list_releases"))

	db.session.delete(release)
	db.session.commit()

	if release.file_path and os.path.isfile(release.file_path):
		os.remove(release.file_path)

	return redirect(package.get_url("packages.view"))


class PackageUpdateConfigFrom(FlaskForm):
	trigger = RadioField(lazy_gettext("Trigger"), [InputRequired()],
			choices=[(PackageUpdateTrigger.COMMIT, lazy_gettext("New Commit")),
					(PackageUpdateTrigger.TAG, lazy_gettext("New Tag"))],
			coerce=PackageUpdateTrigger.coerce, default=PackageUpdateTrigger.TAG)
	ref     = StringField(lazy_gettext("Branch name"), [Optional()], default=None)
	action  = RadioField(lazy_gettext("Action"), [InputRequired()],
			choices=[("notification", lazy_gettext("Send notification and mark as outdated")), ("make_release", lazy_gettext("Create release"))],
			default="make_release")
	submit  = SubmitField(lazy_gettext("Save Settings"))
	disable = SubmitField(lazy_gettext("Disable Automation"))


def set_update_config(package, form):
	if package.update_config is None:
		package.update_config = PackageUpdateConfig()
		db.session.add(package.update_config)

	form.populate_obj(package.update_config)
	package.update_config.ref = nonempty_or_none(form.ref.data)
	package.update_config.make_release = form.action.data == "make_release"

	if package.update_config.trigger == PackageUpdateTrigger.COMMIT:
		if package.update_config.last_commit is None:
			last_release = package.releases.first()
			if last_release and last_release.commit_hash:
				package.update_config.last_commit = last_release.commit_hash
	elif package.update_config.trigger == PackageUpdateTrigger.TAG:
		# Only create releases for tags created after this
		package.update_config.last_commit = None
		package.update_config.last_tag = None

	package.update_config.outdated_at = None
	package.update_config.auto_created = False

	db.session.commit()

	# if package.update_config.last_commit is None:
	check_update_config.delay(package.id)


@bp.route("/packages/<author>/<name>/update-config/", methods=["GET", "POST"])
@login_required
@is_package_page
def update_config(package):
	if not package.check_perm(current_user, Permission.MAKE_RELEASE):
		abort(403)

	if not package.repo:
		flash(gettext("Please add a Git repository URL in order to set up automatic releases"), "danger")
		return redirect(package.get_url("packages.create_edit"))

	form = PackageUpdateConfigFrom(obj=package.update_config)
	if request.method == "GET":
		if package.update_config:
			form.action.data = "make_release" if package.update_config.make_release else "notification"
		elif request.args.get("action") == "notification":
			form.trigger.data = PackageUpdateTrigger.COMMIT
			form.action.data = "notification"

		if "trigger" in request.args:
			form.trigger.data = PackageUpdateTrigger.get(request.args["trigger"])

	if form.validate_on_submit():
		if form.disable.data:
			flash(gettext("Deleted update configuration"), "success")
			if package.update_config:
				db.session.delete(package.update_config)
			db.session.commit()
		else:
			set_update_config(package, form)

		if not form.disable.data and package.releases.count() == 0:
			flash(gettext("Now, please create an initial release"), "success")
			return redirect(package.get_url("packages.create_release"))

		return redirect(package.get_url("packages.list_releases"))

	return render_template("packages/update_config.html", package=package, form=form)


@bp.route("/packages/<author>/<name>/setup-releases/")
@login_required
@is_package_page
def setup_releases(package):
	if not package.check_perm(current_user, Permission.MAKE_RELEASE):
		abort(403)

	if package.update_config:
		return redirect(package.get_url("packages.update_config"))

	return render_template("packages/release_wizard.html", package=package)


@bp.route("/user/update-configs/")
@bp.route("/users/<username>/update-configs/", methods=["GET", "POST"])
@login_required
def bulk_update_config(username=None):
	if username is None:
		return redirect(url_for("packages.bulk_update_config", username=current_user.username))

	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if current_user != user and not current_user.rank.at_least(UserRank.EDITOR):
		abort(403)

	form = PackageUpdateConfigFrom()
	if form.validate_on_submit():
		for package in user.packages.filter(Package.state != PackageState.DELETED, Package.repo.isnot(None)).all():
			set_update_config(package, form)

		return redirect(url_for("packages.bulk_update_config", username=username))

	confs = user.packages \
		.filter(Package.state != PackageState.DELETED,
			Package.update_config.has()) \
		.order_by(db.asc(Package.title)).all()

	return render_template("packages/bulk_update_conf.html", user=user, confs=confs, form=form)
