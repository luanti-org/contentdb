# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from celery import uuid
from flask import redirect, url_for, abort, render_template, flash
from flask_babel import gettext
from flask_login import current_user, login_required
from sqlalchemy import or_, and_

from app.models import User, Package, PackageState, PackageScreenshot, PackageUpdateConfig, ForumTopic, db, \
	PackageRelease, Permission, NotificationType, AuditSeverity, UserRank, PackageType
from app.tasks.importtasks import make_vcs_release
from app.utils.models import add_notification, add_audit_log
from . import bp


@bp.route("/user/tags/")
def tags_user():
	return redirect(url_for('todo.tags', author=current_user.username))


@bp.route("/user/todo/")
@bp.route("/users/<username>/todo/")
@login_required
def view_user(username=None):
	if username is None:
		return redirect(url_for("todo.view_user", username=current_user.username))

	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if current_user != user and not current_user.rank.at_least(UserRank.APPROVER):
		abort(403)

	unapproved_packages = user.packages \
			.filter(or_(Package.state == PackageState.WIP,
				Package.state == PackageState.CHANGES_NEEDED)) \
			.order_by(db.asc(Package.created_at)).all()

	outdated_packages = user.maintained_packages \
			.filter(Package.state != PackageState.DELETED,
					Package.update_config.has(PackageUpdateConfig.outdated_at.isnot(None))) \
			.order_by(db.asc(Package.title)).all()

	missing_game_support = user.maintained_packages.filter(
			Package.state != PackageState.DELETED,
			Package.type.in_([PackageType.MOD, PackageType.TXP]),
			~Package.supported_games.any(),
			Package.supports_all_games == False) \
			.order_by(db.asc(Package.title)).all()

	packages_with_no_screenshots = user.maintained_packages.filter(
			~Package.screenshots.any(), Package.state == PackageState.APPROVED).all()

	packages_with_small_screenshots = user.maintained_packages \
			.filter(Package.state != PackageState.DELETED,
					Package.screenshots.any(and_(PackageScreenshot.width < PackageScreenshot.SOFT_MIN_SIZE[0],
					PackageScreenshot.height < PackageScreenshot.SOFT_MIN_SIZE[1]))) \
			.all()

	topics_to_add = ForumTopic.query \
			.filter_by(author_id=user.id) \
			.filter(~ db.exists().where(Package.forums == ForumTopic.topic_id)) \
			.order_by(db.asc(ForumTopic.name), db.asc(ForumTopic.title)) \
			.all()

	needs_tags = user.maintained_packages \
		.filter(Package.state != PackageState.DELETED, ~Package.tags.any()) \
		.order_by(db.asc(Package.title)).all()

	return render_template("todo/user.html", current_tab="user", user=user,
			unapproved_packages=unapproved_packages, outdated_packages=outdated_packages,
			missing_game_support=missing_game_support, needs_tags=needs_tags, topics_to_add=topics_to_add,
			packages_with_no_screenshots=packages_with_no_screenshots,
			packages_with_small_screenshots=packages_with_small_screenshots,
			screenshot_min_size=PackageScreenshot.HARD_MIN_SIZE, screenshot_rec_size=PackageScreenshot.SOFT_MIN_SIZE)


@bp.route("/users/<username>/update-configs/apply-all/", methods=["POST"])
@login_required
def apply_all_updates(username):
	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if current_user != user and not current_user.rank.at_least(UserRank.EDITOR):
		abort(403)

	outdated_packages = user.maintained_packages \
		.filter(Package.state != PackageState.DELETED,
			Package.update_config.has(PackageUpdateConfig.outdated_at.isnot(None))) \
		.order_by(db.asc(Package.title)).all()

	for package in outdated_packages:
		if not package.check_perm(current_user, Permission.MAKE_RELEASE):
			continue

		if package.releases.filter(or_(PackageRelease.task_id.isnot(None),
				PackageRelease.commit_hash == package.update_config.last_commit)).count() > 0:
			continue

		title = package.update_config.title
		ref = package.update_config.get_ref()

		rel = PackageRelease()
		rel.package = package
		rel.name = title
		rel.title = title
		rel.url = ""
		rel.task_id = uuid()
		db.session.add(rel)
		db.session.commit()

		make_vcs_release.apply_async((rel.id, ref),
									 task_id=rel.task_id)

		msg = "Created release {} (Applied all Git Update Detection)".format(rel.title)
		add_notification(package.maintainers, current_user, NotificationType.PACKAGE_EDIT, msg,
				package.get_url("packages.create_edit"), package)
		add_audit_log(AuditSeverity.NORMAL, current_user, msg, package.get_url("packages.view"), package)
		db.session.commit()

	return redirect(url_for("todo.view_user", username=username))


@bp.route("/user/game_support/")
@bp.route("/users/<username>/game_support/")
@login_required
def all_game_support(username=None):
	if username is None:
		return redirect(url_for("todo.all_game_support", username=current_user.username))

	user: User = User.query.filter_by(username=username).one_or_404()
	if current_user != user and not current_user.rank.at_least(UserRank.EDITOR):
		abort(403)

	packages = user.maintained_packages.filter(
				Package.state != PackageState.DELETED,
				Package.type.in_([PackageType.MOD, PackageType.TXP])) \
			.order_by(db.asc(Package.title)).all()

	bulk_support_names = db.session.query(Package.title) \
		.select_from(Package).filter(
			Package.maintainers.contains(user),
			Package.state != PackageState.DELETED,
			Package.type.in_([PackageType.MOD, PackageType.TXP]),
			~Package.supported_games.any(),
			Package.supports_all_games == False) \
		.order_by(db.asc(Package.title)).all()

	bulk_support_names = ", ".join([x[0] for x in bulk_support_names])

	return render_template("todo/game_support.html", user=user, packages=packages, bulk_support_names=bulk_support_names)


@bp.route("/users/<username>/confirm_supports_all_games/", methods=["POST"])
@login_required
def confirm_supports_all_games(username=None):
	user: User = User.query.filter_by(username=username).one_or_404()
	if current_user != user and not current_user.rank.at_least(UserRank.EDITOR):
		abort(403)

	packages = user.maintained_packages.filter(
		Package.state != PackageState.DELETED,
		Package.type.in_([PackageType.MOD, PackageType.TXP]),
		~Package.supported_games.any(),
		Package.supports_all_games == False) \
		.all()

	for package in packages:
		package.supports_all_games = True
		db.session.merge(package)

		add_audit_log(AuditSeverity.NORMAL, current_user, "Enabled 'Supports all games' (bulk)",
					  package.get_url("packages.game_support"), package)

	db.session.commit()

	flash(gettext("Done"), "success")
	return redirect(url_for("todo.all_game_support", username=current_user.username))
