# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import typing
from urllib.parse import quote as urlescape

from celery import uuid
from flask import render_template, make_response, request, redirect, flash, url_for, abort
from flask_babel import gettext, lazy_gettext
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from jinja2.utils import markupsafe
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import joinedload, subqueryload
from wtforms import SelectField, StringField, TextAreaField, IntegerField, SubmitField, BooleanField
from wtforms.validators import InputRequired, Length, Regexp, DataRequired, Optional, URL, NumberRange, ValidationError
from wtforms_sqlalchemy.fields import QuerySelectField, QuerySelectMultipleField

from app.logic.LogicError import LogicError
from app.logic.packages import do_edit_package
from app.querybuilder import QueryBuilder
from app.rediscache import has_key, set_temp_key
from app.tasks.importtasks import import_repo_screenshot, check_zip_release, remove_package_game_support, \
	update_package_game_support
from app.tasks.pkgtasks import check_package_on_submit
from app.tasks.webhooktasks import post_discord_webhook

from . import bp, get_package_tabs
from app.models import Package, Tag, db, User, Tags, PackageState, Permission, PackageType, MetaPackage, ForumTopic, \
	Dependency, Thread, UserRank, PackageReview, PackageDevState, ContentWarning, License, AuditSeverity, \
	PackageScreenshot, NotificationType, AuditLogEntry, PackageAlias, PackageProvides, PackageGameSupport, \
	PackageDailyStats, Collection, ReleaseState, PackageAIDisclosure
from app.utils.models import is_package_page, add_audit_log, get_package_by_info, \
	add_notification, get_system_user, get_games_from_csv, \
	post_to_approval_thread
from app.utils.user import rank_required
from app.utils.flask import is_user_bot, get_int_or_abort, abs_url_for, get_daterange_options
from app.utils.misc import normalize_line_endings
from app.logic.package_approval import validate_package_for_approval, can_move_to_state
from app.logic.game_support import game_support_set
from app.utils.models import create_session


@bp.route("/packages/")
def list_all():
	qb    = QueryBuilder(request.args, cookies=True)
	query = qb.build_package_query()
	title = qb.title

	query = query.options(
			joinedload(Package.license),
			joinedload(Package.media_license),
			subqueryload(Package.tags))

	ip = request.headers.get("X-Forwarded-For") or request.remote_addr
	if ip is not None and not is_user_bot() and len(qb.tags) == 1:
		tag = qb.tags[0]
		key = "tag/{}/{}".format(ip, tag.name)
		if not has_key(key):
			set_temp_key(key, "true")
			with create_session() as new_session:
				new_session.query(Tag).filter_by(id=tag.id).update({
						"views": Tag.views + 1
					})
				new_session.commit()

	if qb.lucky:
		package = query.first()
		if package:
			return redirect(package.get_url("packages.view"))

		topic = qb.build_topic_query().first()
		if qb.search and topic:
			return redirect(topic.url)

	page  = get_int_or_abort(request.args.get("page"), 1)
	num   = min(40, get_int_or_abort(request.args.get("n"), 100))
	query = query.paginate(page=page, per_page=num)

	search = request.args.get("q")
	type_name = request.args.get("type")

	authors = []
	if search:
		authors = User.query \
			.filter(or_(*[func.lower(User.username) == name.lower().strip() for name in search.split(" ")])) \
			.all()

		authors = [(author.username, search.lower().replace(author.username.lower(), "")) for author in authors]

	topics = None
	if qb.search and not query.has_next:
		topics = qb.build_topic_query().all()

	tags_query = db.session.query(func.count(Tags.c.tag_id), Tag) \
		.select_from(Tag).join(Tags).join(Package).filter(Package.state==PackageState.APPROVED) \
		.group_by(Tag.id).order_by(db.asc(Tag.title))
	tags = qb.filter_package_query(tags_query).all()

	selected_tags = set(qb.tags)

	return render_template("packages/list.html",
			query_hint=qb.query_hint, packages=query.items, pagination=query,
			query=search, tags=tags, selected_tags=selected_tags, type=type_name,
			authors=authors, packages_count=query.total, topics=topics, noindex=qb.noindex)


def get_releases(package):
	if package.check_perm(current_user, Permission.MAKE_RELEASE):
		return package.releases.limit(5)
	else:
		return package.releases.filter_by(state=ReleaseState.APPROVED).limit(5)


@bp.route("/packages/<author>/")
def user_redirect(author):
	return redirect(url_for("users.profile", username=author))


@bp.route("/packages/<author>/<name>/")
@is_package_page
def view(package):
	if not package.check_perm(current_user, Permission.VIEW_PACKAGE):
		return render_template("packages/gone.html", package=package), 403

	packages_uses = None
	if package.type == PackageType.MOD:
		packages_uses = Package.query.filter(
				Package.type == PackageType.MOD,
				Package.id != package.id,
				Package.state == PackageState.APPROVED,
				Package.dependencies.any(
						Dependency.meta_package_id.in_([p.id for p in package.provides]))) \
			.order_by(db.desc(Package.score)).limit(6).all()

	releases = get_releases(package)

	review_thread = package.review_thread
	if review_thread is not None and not review_thread.check_perm(current_user, Permission.SEE_THREAD):
		review_thread = None

	threads = Thread.query.filter_by(package_id=package.id, review_id=None)
	if not current_user.is_authenticated:
		threads = threads.filter_by(private=False)
	elif not current_user.rank.at_least(UserRank.APPROVER) and not current_user == package.author:
		threads = threads.filter(or_(Thread.private == False, Thread.author == current_user))

	has_review = current_user.is_authenticated and \
		PackageReview.query.filter_by(package=package, author=current_user).count() > 0

	validation = None
	if package.state != PackageState.APPROVED:
		validation = validate_package_for_approval(package)

	favorites_count = Collection.query.filter(
			Collection.packages.contains(package),
			Collection.name == "favorites").count()

	public_collection_count = Collection.query.filter(
		Collection.packages.contains(package),
		Collection.private == False).count()

	is_favorited = current_user.is_authenticated and \
		Collection.query.filter(
			Collection.author == current_user,
			Collection.packages.contains(package),
			Collection.name == "favorites").count() > 0

	return render_template("packages/view.html",
			package=package, releases=releases, packages_uses=packages_uses,
			review_thread=review_thread, threads=threads.all(), validation=validation,
			has_review=has_review, favorites_count=favorites_count, is_favorited=is_favorited,
			public_collection_count=public_collection_count)


@bp.route("/packages/<author>/<name>/shields/<type>/")
@is_package_page
def shield(package, type):
	if type == "title":
		url = "https://img.shields.io/static/v1?label=ContentDB&message={}&color={}" \
			.format(urlescape(package.title), urlescape("#375a7f"))
	elif type == "downloads":
		api_url = abs_url_for("api.package_view", author=package.author.username, name=package.name)
		url = "https://img.shields.io/badge/dynamic/json?color={}&label=ContentDB&query=downloads&suffix=+downloads&url={}" \
			.format(urlescape("#375a7f"), urlescape(api_url))
	else:
		from flask import abort
		abort(404)

	return redirect(url)


@bp.route("/packages/<author>/<name>/download/")
@is_package_page
def download(package):
	release = package.get_download_release()

	if release is None:
		if "application/zip" in request.accept_mimetypes and \
				"text/html" not in request.accept_mimetypes:
			return "", 204
		else:
			flash(gettext("No download available."), "danger")
			return redirect(package.get_url("packages.view"))
	else:
		return redirect(release.get_download_url())


def make_label(obj: Tag | ContentWarning):
	translated = obj.get_translated()
	if translated["description"]:
		return "{}: {}".format(translated["title"], translated["description"])
	else:
		return translated["title"]


class PackageForm(FlaskForm):
	type             = SelectField(lazy_gettext("Type"), [InputRequired()], choices=PackageType.choices(), coerce=PackageType.coerce, default=PackageType.MOD)
	title            = StringField(lazy_gettext("Title (Human-readable)"), [InputRequired(), Length(1, 100)])
	name             = StringField(lazy_gettext("Name (Technical)"), [InputRequired(), Length(1, 100), Regexp("^[a-z0-9_]+$", 0, lazy_gettext("Lower case letters (a-z), digits (0-9), and underscores (_) only"))])
	short_desc       = StringField(lazy_gettext("Short Description (Plaintext)"), [InputRequired(), Length(1,200)])

	dev_state = SelectField(lazy_gettext("Maintenance State"), [DataRequired()], choices=PackageDevState.choices(with_none=True), coerce=PackageDevState.coerce)
	ai_disclosure = SelectField(lazy_gettext("AI Disclosure"), [DataRequired()], choices=PackageAIDisclosure.choices(), coerce=PackageAIDisclosure.coerce)

	tags             = QuerySelectMultipleField(lazy_gettext('Tags'), query_factory=lambda: Tag.query.order_by(db.asc(Tag.name)), get_pk=lambda a: a.id, get_label=make_label)
	content_warnings = QuerySelectMultipleField(lazy_gettext('Content Warnings'), query_factory=lambda: ContentWarning.query.order_by(db.asc(ContentWarning.name)), get_pk=lambda a: a.id, get_label=make_label)
	license          = QuerySelectField(lazy_gettext("License"), [DataRequired()], allow_blank=True, query_factory=lambda: License.query.order_by(db.asc(License.name)), get_pk=lambda a: a.id, get_label=lambda a: a.name)
	media_license    = QuerySelectField(lazy_gettext("Media License"), [DataRequired()], allow_blank=True, query_factory=lambda: License.query.order_by(db.asc(License.name)), get_pk=lambda a: a.id, get_label=lambda a: a.name)

	desc             = TextAreaField(lazy_gettext("Long Description (Markdown)"), [Optional(), Length(0,10000)], filters=[normalize_line_endings])

	repo             = StringField(lazy_gettext("VCS Repository URL"), [Optional(), URL()], filters = [lambda x: x or None])
	website          = StringField(lazy_gettext("Website URL"), [Optional(), URL()], filters = [lambda x: x or None])
	issueTracker     = StringField(lazy_gettext("Issue Tracker URL"), [Optional(), URL()], filters = [lambda x: x or None])
	forums           = IntegerField(lazy_gettext("Forum Topic ID"), [Optional(), NumberRange(0, 999999)])
	video_url        = StringField(lazy_gettext("Video URL"), [Optional(), URL()], filters=[lambda x: x or None])
	donate_url       = StringField(lazy_gettext("Donate URL"), [Optional(), URL()], filters=[lambda x: x or None])
	translation_url  = StringField(lazy_gettext("Translation URL"), [Optional(), URL()], filters=[lambda x: x or None])

	submit           = SubmitField(lazy_gettext("Save"))

	def validate_name(self, field):
		if field.data == "_game":
			raise ValidationError(lazy_gettext("_game is not an allowed name"))


def handle_create_edit(package: typing.Optional[Package], form: PackageForm, author: User):
	wasNew = False
	if package is None:
		package = Package.query.filter_by(name=form.name.data, author_id=author.id).first()
		if package is not None:
			if package.state == PackageState.DELETED:
				flash(
					gettext("Package already exists, but is removed. Please contact ContentDB staff to restore the package"),
					"danger")
				return redirect(url_for("report.report", url=package.get_url("packages.view")))
			else:
				flash(markupsafe.Markup(
					f"<a class='btn btn-sm btn-danger float-end' href='{package.get_url('packages.view')}'>View</a>" +
					gettext("Package already exists")), "danger")
			return None

		if Collection.query \
				.filter(Collection.name == form.name.data, Collection.author == author) \
				.count() > 0:
			flash(gettext("A collection with a similar name already exists"), "danger")
			return

		package = Package()
		db.session.add(package)
		package.author = author
		package.maintainers.append(author)
		wasNew = True

	try:
		do_edit_package(current_user, package, wasNew, True, {
			"type": form.type.data,
			"title": form.title.data,
			"name": form.name.data,
			"short_desc": form.short_desc.data,
			"dev_state": form.dev_state.data,
			"ai_disclosure": form.ai_disclosure.data,
			"tags": form.tags.raw_data,
			"content_warnings": form.content_warnings.raw_data,
			"license": form.license.data,
			"media_license": form.media_license.data,
			"desc": form.desc.data,
			"repo": form.repo.data,
			"website": form.website.data,
			"issueTracker": form.issueTracker.data,
			"forums": form.forums.data,
			"video_url": form.video_url.data,
			"donate_url": form.donate_url.data,
			"translation_url": form.translation_url.data,
		})

		if wasNew and package.repo is not None:
			import_repo_screenshot.delay(package.id)

		next_url = package.get_url("packages.view")
		if wasNew and ("WTFPL" in package.license.name or "WTFPL" in package.media_license.name):
			next_url = url_for("flatpage", path="help/wtfpl", r=next_url)
		elif wasNew:
			next_url = package.get_url("packages.setup_releases")

		return redirect(next_url)
	except LogicError as e:
		flash(e.message, "danger")
		db.session.rollback()


@bp.route("/packages/new/", methods=["GET", "POST"])
@bp.route("/packages/<author>/<name>/edit/", methods=["GET", "POST"])
@login_required
def create_edit(author=None, name=None):
	if current_user.email is None and not current_user.rank.at_least(UserRank.ADMIN):
		flash(gettext("You must add an email address to your account and confirm it before you can manage packages"), "danger")
		return redirect(url_for("users.email_notifications"))

	package = None
	if author is None:
		form = PackageForm(formdata=request.form)
		form.submit.label.text = lazy_gettext("Save draft")

		author = request.args.get("author")
		if author is None or author == current_user.username:
			author = current_user
		else:
			author = User.query.filter_by(username=author).first()
			if author is None:
				flash(gettext("Unable to find that user"), "danger")
				return redirect(url_for("packages.create_edit"))

			if not author.check_perm(current_user, Permission.CHANGE_AUTHOR):
				flash(gettext("Permission denied"), "danger")
				return redirect(url_for("packages.create_edit"))

	else:
		package = get_package_by_info(author, name)
		if package is None:
			abort(404)
		if not package.check_perm(current_user, Permission.EDIT_PACKAGE):
			abort(403)

		author = package.author

		form = PackageForm(formdata=request.form, obj=package)

	# Initial form class from post data and default data
	if request.method == "GET":
		if package is None:
			form.name.data = request.args.get("bname")
			form.title.data = request.args.get("title")
			form.repo.data = request.args.get("repo")
			form.forums.data = request.args.get("forums")
			form.license.data = None
			form.media_license.data = None
		else:
			form.tags.data = package.tags
			form.content_warnings.data = package.content_warnings

	if request.method == "POST" and form.type.data == PackageType.TXP:
		form.license.data = form.media_license.data

	if form.validate_on_submit():
		ret = handle_create_edit(package, form, author)
		if ret:
			return ret

	package_query = Package.query.filter_by(state=PackageState.APPROVED)
	if package is not None:
		package_query = package_query.filter(Package.id != package.id)

	enableWizard = name is None and request.method != "POST"
	return render_template("packages/create_edit.html", package=package,
			form=form, author=author, enable_wizard=enableWizard,
			packages=package_query.all(),
			modnames=MetaPackage.query.order_by(db.asc(MetaPackage.name)).all(),
			tabs=get_package_tabs(current_user, package), current_tab="edit")


@bp.route("/packages/<author>/<name>/state/", methods=["POST"])
@login_required
@is_package_page
def move_to_state(package):
	state = PackageState.get(request.args.get("state"))
	if state is None:
		abort(400)

	if package.state == state:
		return redirect(package.get_url("packages.view"))

	if not can_move_to_state(package, current_user, state):
		flash(gettext("You don't have permission to do that"), "danger")
		return redirect(package.get_url("packages.view"))

	old_state = package.state
	package.state = state
	msg = "Marked {} as {}".format(package.title, state.value)

	if state == PackageState.APPROVED:
		if not package.approved_at:
			post_discord_webhook.delay(package.author.display_name,
					"New package {}".format(package.get_url("packages.view", absolute=True)), False,
					package.title, package.short_desc, package.get_thumb_url(2, True, "png"))
			package.approved_at = datetime.datetime.now()

		screenshots = PackageScreenshot.query.filter_by(package=package, approved=False).all()
		for s in screenshots:
			s.approved = True

		msg = "Approved {}".format(package.title)
		update_package_game_support.delay(package.id)
	elif state == PackageState.READY_FOR_REVIEW:
		post_discord_webhook.delay(package.author.display_name,
				"Ready for Review: {}".format(package.get_url("packages.view", absolute=True)), True,
				package.title, package.short_desc, package.get_thumb_url(2, True, "png"))

	add_notification(package.maintainers, current_user, NotificationType.PACKAGE_APPROVAL, msg, package.get_url("packages.view"), package)
	severity = AuditSeverity.NORMAL if current_user in package.maintainers else AuditSeverity.EDITOR
	add_audit_log(severity, current_user, msg, package.get_url("packages.view"), package)
	post_to_approval_thread(package, current_user, msg, True)

	db.session.commit()

	check_package_on_submit.delay(package.id)

	if package.state == PackageState.CHANGES_NEEDED:
		flash(gettext("Please comment what changes are needed in the approval thread"), "warning")
		if package.review_thread:
			return redirect(package.review_thread.get_view_url())
		else:
			return redirect(url_for('threads.new', author=package.author.username, name=package.name, title='Package approval comments'))
	elif (package.review_thread and
			old_state == PackageState.CHANGES_NEEDED and package.state == PackageState.READY_FOR_REVIEW):
		flash(gettext("Please comment in the approval thread so editors know what you have changed"), "warning")
		return redirect(package.review_thread.get_view_url())

	return redirect(package.get_url("packages.view"))


@bp.route("/packages/<author>/<name>/translation/")
@login_required
@is_package_page
def translation(package):
	return render_template("packages/translation.html", package=package,
			has_content_translations=any([x.title or x.short_desc for x in package.translations.all()]),
			tabs=get_package_tabs(current_user, package), current_tab="translation")


@bp.route("/packages/<author>/<name>/remove/", methods=["GET", "POST"])
@login_required
@is_package_page
def remove(package):
	if not package.check_perm(current_user, Permission.EDIT_PACKAGE):
		abort(403)

	states = [PackageDevState.AS_IS, PackageDevState.DEPRECATED, PackageDevState.LOOKING_FOR_MAINTAINER]

	if request.method == "GET":
		# Find packages that will having missing hard deps after this action
		broken_meta = MetaPackage.query.filter(MetaPackage.packages.contains(package),
				~MetaPackage.packages.any(and_(Package.id != package.id, Package.state == PackageState.APPROVED)))
		hard_deps = Package.query.filter(
			Package.state == PackageState.APPROVED,
			Package.dependencies.any(
				and_(Dependency.meta_package_id.in_([x.id for x in broken_meta]), Dependency.optional == False))).all()

		return render_template("packages/remove.html",
				package=package, hard_deps=hard_deps, states=states,
				tabs=get_package_tabs(current_user, package), current_tab="remove")

	for state in states:
		if state.name in request.form:
			flash(gettext("Set state to %(state)s", state=state.title), "success")
			package.dev_state = state
			msg = "Set dev state of {} to {}".format(package.title, state.title)
			add_audit_log(AuditSeverity.NORMAL, current_user, msg, package.get_url("packages.view"), package)
			db.session.commit()
			return redirect(package.get_url("packages.view"))

	reason = request.form.get("reason") or "?"
	if len(reason) > 500:
		abort(400)

	if "delete" in request.form:
		if not package.check_perm(current_user, Permission.DELETE_PACKAGE):
			flash(gettext("You don't have permission to do that"), "danger")
			return redirect(package.get_url("packages.view"))

		package.state = PackageState.DELETED

		url = url_for("users.profile", username=package.author.username)
		msg = "Deleted {}, reason={}".format(package.title, reason)
		add_notification(package.maintainers, current_user, NotificationType.PACKAGE_EDIT, msg, url, package)
		add_audit_log(AuditSeverity.EDITOR, current_user, msg, url, package)
		db.session.commit()

		post_discord_webhook.delay(current_user.username,
			f"Deleted package {package.author.username}/{package.name} with reason '{reason}'",
			True, package.title, package.short_desc, package.get_thumb_url(2, True, "png"))

		remove_package_game_support.delay(package.id)

		flash(gettext("Deleted package"), "success")

		return redirect(url)
	elif "unapprove" in request.form:
		if not package.check_perm(current_user, Permission.UNAPPROVE_PACKAGE):
			flash(gettext("You don't have permission to do that"), "danger")
			return redirect(package.get_url("packages.view"))

		package.state = PackageState.WIP

		msg = "Unapproved {}, reason={}".format(package.title, reason)
		add_notification(package.maintainers, current_user, NotificationType.PACKAGE_APPROVAL, msg, package.get_url("packages.view"), package)
		add_audit_log(AuditSeverity.EDITOR, current_user, msg, package.get_url("packages.view"), package)

		db.session.commit()

		post_discord_webhook.delay(current_user.username,
			"Unapproved package with reason {}\n\n{}".format(reason, package.get_url("packages.view", absolute=True)), True,
			package.title, package.short_desc, package.get_thumb_url(2, True, "png"))

		remove_package_game_support.delay(package.id)

		flash(gettext("Unapproved package"), "success")

		return redirect(package.get_url("packages.view"))
	else:
		abort(400)



class PackageMaintainersForm(FlaskForm):
	maintainers_str  = StringField(lazy_gettext("Maintainers (Comma-separated)"), [Optional()])
	submit	      = SubmitField(lazy_gettext("Save"))


@bp.route("/packages/<author>/<name>/edit-maintainers/", methods=["GET", "POST"])
@login_required
@is_package_page
def edit_maintainers(package):
	if not package.check_perm(current_user, Permission.EDIT_MAINTAINERS):
		flash(gettext("You don't have permission to edit maintainers"), "danger")
		return redirect(package.get_url("packages.view"))

	form = PackageMaintainersForm(formdata=request.form)
	if request.method == "GET":
		form.maintainers_str.data = ", ".join([ x.username for x in package.maintainers if x != package.author ])

	if form.validate_on_submit():
		usernames = [x.strip().lower() for x in form.maintainers_str.data.split(",")]
		users = User.query.filter(func.lower(User.username).in_(usernames)).all()

		thread = package.threads.filter_by(author=get_system_user()).first()

		for user in users:
			if not user in package.maintainers:
				if thread and user not in thread.watchers:
					thread.watchers.append(user)
				add_notification(user, current_user, NotificationType.MAINTAINER,
						"Added you as a maintainer of {}".format(package.title), package.get_url("packages.view"), package)

		for user in package.maintainers:
			if user != package.author and not user in users:
				add_notification(user, current_user, NotificationType.MAINTAINER,
						"Removed you as a maintainer of {}".format(package.title), package.get_url("packages.view"), package)

		package.maintainers.clear()
		package.maintainers.extend(users)
		if package.author not in package.maintainers:
			package.maintainers.append(package.author)

		msg = "Edited {} maintainers".format(package.title)
		add_notification(package.author, current_user, NotificationType.MAINTAINER, msg, package.get_url("packages.view"), package)
		severity = AuditSeverity.NORMAL if current_user == package.author else AuditSeverity.MODERATION
		add_audit_log(severity, current_user, msg, package.get_url("packages.view"), package)

		db.session.commit()

		return redirect(package.get_url("packages.view"))

	users = User.query.filter(User.rank >= UserRank.NEW_MEMBER).order_by(db.asc(User.username)).all()

	return render_template("packages/edit_maintainers.html", package=package, form=form,
			users=users, tabs=get_package_tabs(current_user, package), current_tab="maintainers")


@bp.route("/packages/<author>/<name>/remove-self-maintainer/", methods=["POST"])
@login_required
@is_package_page
def remove_self_maintainers(package):
	if not current_user in package.maintainers:
		flash(gettext("You are not a maintainer"), "danger")

	elif current_user == package.author:
		flash(gettext("Package owners cannot remove themselves as maintainers"), "danger")

	else:
		package.maintainers.remove(current_user)

		add_notification(package.author, current_user, NotificationType.MAINTAINER,
				"Removed themself as a maintainer of {}".format(package.title), package.get_url("packages.view"), package)

		db.session.commit()

	return redirect(package.get_url("packages.view"))


@bp.route("/packages/<author>/<name>/audit/")
@login_required
@is_package_page
def audit(package):
	if not (package.check_perm(current_user, Permission.EDIT_PACKAGE) or
			package.check_perm(current_user, Permission.APPROVE_NEW)):
		abort(403)

	page = get_int_or_abort(request.args.get("page"), 1)
	num = min(40, get_int_or_abort(request.args.get("n"), 100))

	query = package.audit_log_entries.order_by(db.desc(AuditLogEntry.created_at))

	pagination = query.paginate(page=page, per_page=num)
	return render_template("packages/audit.html", log=pagination.items, pagination=pagination,
		package=package, tabs=get_package_tabs(current_user, package), current_tab="audit")


class PackageAliasForm(FlaskForm):
	author  = StringField(lazy_gettext("Author Name"), [InputRequired(), Length(1, 50)])
	name    = StringField(lazy_gettext("Name (Technical)"), [InputRequired(), Length(1, 100),
			Regexp("^[a-z0-9_]+$", 0, lazy_gettext("Lower case letters (a-z), digits (0-9), and underscores (_) only"))])
	submit  = SubmitField(lazy_gettext("Save"))


@bp.route("/packages/<author>/<name>/aliases/")
@rank_required(UserRank.ADMIN)
@is_package_page
def alias_list(package: Package):
	return render_template("packages/alias_list.html", package=package)


@bp.route("/packages/<author>/<name>/aliases/new/", methods=["GET", "POST"])
@bp.route("/packages/<author>/<name>/aliases/<int:alias_id>/", methods=["GET", "POST"])
@rank_required(UserRank.ADMIN)
@is_package_page
def alias_create_edit(package: Package, alias_id: int = None):
	alias = None
	if alias_id:
		alias = PackageAlias.query.get(alias_id)
		if alias is None or alias.package != package:
			abort(404)

	form = PackageAliasForm(request.form, obj=alias)
	if form.validate_on_submit():
		if alias is None:
			alias = PackageAlias()
			alias.package = package
			db.session.add(alias)

		form.populate_obj(alias)
		db.session.commit()

		return redirect(package.get_url("packages.alias_list"))

	return render_template("packages/alias_create_edit.html", package=package, form=form)


@bp.route("/packages/<author>/<name>/share/")
@login_required
@is_package_page
def share(package):
	return render_template("packages/share.html", package=package,
			tabs=get_package_tabs(current_user, package), current_tab="share")


@bp.route("/packages/<author>/<name>/similar/")
@is_package_page
def similar(package):
	packages_modnames = {}
	for mname in package.provides:
		packages_modnames[mname] = Package.query.filter(Package.id != package.id,
				Package.state != PackageState.DELETED) \
			.filter(Package.provides.any(PackageProvides.c.metapackage_id == mname.id)) \
			.order_by(db.desc(Package.score)) \
			.all()

	similar_topics = ForumTopic.query \
		.filter_by(name=package.name) \
		.filter(ForumTopic.topic_id != package.forums) \
		.filter(~ db.exists().where(Package.forums == ForumTopic.topic_id)) \
		.order_by(db.asc(ForumTopic.name), db.asc(ForumTopic.title)) \
		.all()

	return render_template("packages/similar.html", package=package,
			packages_modnames=packages_modnames, similar_topics=similar_topics)


def csv_games_check(_form, field):
	game_names = [name.strip() for name in field.data.split(",")]
	if len(game_names) == 0 or (len(game_names) == 1 and game_names[0] == ""):
		return

	missing = set()
	for game_name in game_names:
		if game_name.endswith("_game"):
			game_name = game_name[:-5]
		if Package.query.filter(and_(Package.state==PackageState.APPROVED, Package.type==PackageType.GAME,
				or_(Package.name==game_name, Package.name==game_name + "_game"))).count() == 0:
			missing.add(game_name)

	if len(missing) > 0:
		raise ValidationError(f"Unable to find game {','.join(missing)}")


class GameSupportForm(FlaskForm):
	enable_support_detection = BooleanField(lazy_gettext("Enable support detection based on dependencies (recommended)"), [Optional()])
	supported = StringField(lazy_gettext("Supported games"), [Optional(), csv_games_check])
	unsupported = StringField(lazy_gettext("Unsupported games"), [Optional(), csv_games_check])
	supports_all_games = BooleanField(lazy_gettext("Supports all games (unless stated) / is game independent"), [Optional()])
	submit = SubmitField(lazy_gettext("Save"))


@bp.route("/packages/<author>/<name>/support/", methods=["GET", "POST"])
@login_required
@is_package_page
def game_support(package):
	if package.type != PackageType.MOD and package.type != PackageType.TXP:
		abort(404)

	can_edit = package.check_perm(current_user, Permission.EDIT_PACKAGE)
	if not (can_edit or package.check_perm(current_user, Permission.APPROVE_NEW)):
		abort(403)

	if package.releases.count() == 0:
		flash(gettext("You need at least one release before you can edit game support"), "danger")
		return redirect(package.get_url('packages.create_release' if package.update_config else 'packages.setup_releases'))

	if package.type == PackageType.MOD and len(package.provides) == 0:
		flash(gettext("Mod(pack) needs to contain at least one mod. Please create a new release"), "danger")
		return redirect(package.get_url('packages.list_releases'))

	force_game_detection = package.supported_games.filter(and_(
		PackageGameSupport.confidence > 1, PackageGameSupport.supports == True)).count() == 0

	can_support_all_games = package.type != PackageType.TXP and \
		package.supported_games.filter(and_(
			PackageGameSupport.confidence == 1, PackageGameSupport.supports == True)).count() == 0

	can_override = can_edit

	form = GameSupportForm() if can_edit else None
	if form and request.method == "GET":
		form.enable_support_detection.data = package.enable_game_support_detection
		form.supports_all_games.data = package.supports_all_games and can_support_all_games

		if can_override:
			manual_supported_games = package.supported_games.filter_by(confidence=11).all()
			form.supported.data = ", ".join([x.game.name for x in manual_supported_games if x.supports])
			form.unsupported.data = ", ".join([x.game.name for x in manual_supported_games if not x.supports])
		else:
			form.supported = None
			form.unsupported = None

	if form and form.validate_on_submit():
		detect_update_needed = False

		if can_override:
			try:
				game_is_supported = {}
				for game in get_games_from_csv(db.session, form.supported.data or ""):
					game_is_supported[game.id] = True
				for game in get_games_from_csv(db.session, form.unsupported.data or ""):
					game_is_supported[game.id] = False
				game_support_set(db.session, package, game_is_supported, 11)
				detect_update_needed = True
			except LogicError as e:
				flash(e.message, "danger")

		next_url = package.get_url("packages.game_support")

		enable_support_detection = form.enable_support_detection.data or force_game_detection
		if enable_support_detection != package.enable_game_support_detection:
			package.enable_game_support_detection = enable_support_detection
			if package.enable_game_support_detection:
				detect_update_needed = True
			else:
				package.supported_games.filter_by(confidence=1).delete()

		if can_support_all_games:
			package.supports_all_games = form.supports_all_games.data

		add_audit_log(AuditSeverity.NORMAL, current_user, "Edited game support", package.get_url("packages.game_support"), package)

		db.session.commit()

		if detect_update_needed:
			release = package.releases.first()
			if release:
				task_id = uuid()
				check_zip_release.apply_async((release.id, release.file_path), task_id=task_id)
				next_url = url_for("tasks.check", id=task_id, r=next_url)

		return redirect(next_url)

	all_game_support = package.supported_games.all()
	all_game_support.sort(key=lambda x: -x.game.score)
	supported_games_list: typing.List[str] = [x.game.name for x in all_game_support if x.supports]
	if package.supports_all_games:
		supported_games_list.insert(0, "*")
	supported_games = ", ".join(supported_games_list)
	unsupported_games = ", ".join([x.game.name for x in all_game_support if not x.supports])

	mod_conf_lines = ""
	if supported_games:
		mod_conf_lines += f"supported_games = {supported_games}"
	if unsupported_games:
		mod_conf_lines += f"\nunsupported_games = {unsupported_games}"

	return render_template("packages/game_support.html", package=package, form=form,
			mod_conf_lines=mod_conf_lines, force_game_detection=force_game_detection,
			can_support_all_games=can_support_all_games, tabs=get_package_tabs(current_user, package),
			current_tab="game_support")


@bp.route("/packages/<author>/<name>/stats/")
@login_required
@is_package_page
def statistics(package):
	start = request.args.get("start")
	end = request.args.get("end")

	return render_template("packages/stats.html",
		package=package, tabs=get_package_tabs(current_user, package), current_tab="stats",
		start=start, end=end, options=get_daterange_options(), noindex=start or end)


@bp.route("/packages/<author>/<name>/stats.csv")
@is_package_page
def stats_csv(package):
	stats: typing.List[PackageDailyStats] = package.daily_stats.order_by(db.asc(PackageDailyStats.date)).all()

	columns = ["platform_minetest", "platform_other", "reason_new",
				"reason_dependency", "reason_update"]

	result = "Date, " + ", ".join(columns) + "\n"

	for stat in stats:
		stat: PackageDailyStats
		result += stat.date.isoformat()
		for i, key in enumerate(columns):
			result += ", " + str(getattr(stat, key))
		result += "\n"

	date = datetime.datetime.utcnow().date()

	res = make_response(result, 200)
	res.headers["Content-Disposition"] = f"attachment; filename={package.author.username}_{package.name}_stats_{date.isoformat()}.csv"
	res.headers["Content-type"] = "text/csv"
	return res
