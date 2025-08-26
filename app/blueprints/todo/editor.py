# ContentDB
# Copyright (C) 2018-23 rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


from flask import redirect, url_for, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_, and_

from app.models import Package, PackageState, PackageScreenshot, PackageUpdateConfig, ForumTopic, db, \
	PackageRelease, Permission, UserRank, License, MetaPackage, Dependency, AuditLogEntry, Tag, LuantiRelease, Report
from app.querybuilder import QueryBuilder
from app.utils import get_int_or_abort, is_yes, rank_required
from . import bp


@bp.route("/todo/", methods=["GET", "POST"])
@login_required
def view_editor():
	can_approve_new = Permission.APPROVE_NEW.check(current_user)
	can_approve_rel = Permission.APPROVE_RELEASE.check(current_user)
	can_approve_scn = Permission.APPROVE_SCREENSHOT.check(current_user)

	packages = None
	wip_packages = None
	if can_approve_new:
		packages = Package.query.filter_by(state=PackageState.READY_FOR_REVIEW) \
			.order_by(db.desc(Package.created_at)).all()
		wip_packages = Package.query \
			.filter(or_(Package.state == PackageState.WIP, Package.state == PackageState.CHANGES_NEEDED)) \
			.order_by(db.desc(Package.created_at)).all()

	releases = None
	if can_approve_rel:
		releases = PackageRelease.query.filter_by(approved=False, task_id=None).all()

	screenshots = None
	if can_approve_scn:
		screenshots = PackageScreenshot.query.filter_by(approved=False).all()

	if not can_approve_new and not can_approve_rel and not can_approve_scn:
		abort(403)

	if request.method == "POST":
		if request.form["action"] == "screenshots_approve_all":
			if not can_approve_scn:
				abort(403)

			PackageScreenshot.query.update({"approved": True})
			db.session.commit()
			return redirect(url_for("todo.view_editor"))
		else:
			abort(400)

	license_needed = Package.query \
		.filter(Package.state.in_([PackageState.READY_FOR_REVIEW, PackageState.APPROVED])) \
		.filter(or_(Package.license.has(License.name.like("Other %")),
			Package.media_license.has(License.name.like("Other %")))) \
		.all()

	total_packages = Package.query.filter_by(state=PackageState.APPROVED).count()
	total_to_tag = Package.query.filter_by(state=PackageState.APPROVED, tags=None).count()

	unfulfilled_meta_packages = MetaPackage.query \
		.filter(~ MetaPackage.packages.any(state=PackageState.APPROVED)) \
		.filter(MetaPackage.dependencies.any(Dependency.depender.has(state=PackageState.APPROVED), optional=False)) \
		.order_by(db.asc(MetaPackage.name)).count()

	audit_log = AuditLogEntry.query \
		.filter(AuditLogEntry.package.has()) \
		.order_by(db.desc(AuditLogEntry.created_at)) \
		.limit(20).all()

	reports = Report.query.filter_by(is_resolved=False).order_by(db.asc(Report.created_at)).all() if current_user.rank.at_least(UserRank.EDITOR) else None

	return render_template("todo/editor.html", current_tab="editor",
			packages=packages, wip_packages=wip_packages, releases=releases, screenshots=screenshots,
			can_approve_new=can_approve_new, can_approve_rel=can_approve_rel, can_approve_scn=can_approve_scn,
			license_needed=license_needed, total_packages=total_packages, total_to_tag=total_to_tag,
			unfulfilled_meta_packages=unfulfilled_meta_packages, audit_log=audit_log, reports=reports)


@bp.route("/todo/tags/")
@login_required
def tags():
	qb    = QueryBuilder(request.args, cookies=True)
	qb.set_sort_if_none("score", "desc")
	query = qb.build_package_query()

	only_no_tags = is_yes(request.args.get("no_tags"))
	if only_no_tags:
		query = query.filter(Package.tags == None)

	tags = Tag.query.order_by(db.asc(Tag.title)).all()

	return render_template("todo/tags.html", current_tab="tags", packages=query.all(),
			tags=tags, only_no_tags=only_no_tags)


@bp.route("/todo/modnames/")
@login_required
def modnames():
	mnames = MetaPackage.query \
			.filter(~ MetaPackage.packages.any(state=PackageState.APPROVED)) \
			.filter(MetaPackage.dependencies.any(Dependency.depender.has(state=PackageState.APPROVED), optional=False)) \
			.order_by(db.asc(MetaPackage.name)).all()

	return render_template("todo/modnames.html", modnames=mnames)


@bp.route("/todo/outdated/")
@login_required
def outdated():
	is_mtm_only = is_yes(request.args.get("mtm"))

	query = db.session.query(Package).select_from(PackageUpdateConfig) \
			.filter(PackageUpdateConfig.outdated_at.isnot(None)) \
			.join(PackageUpdateConfig.package) \
			.filter(Package.state == PackageState.APPROVED)

	if is_mtm_only:
		query = query.filter(Package.repo.ilike("%github.com/minetest-mods/%"))

	sort_by = request.args.get("sort")
	if sort_by == "date":
		query = query.order_by(db.desc(PackageUpdateConfig.outdated_at))
	else:
		sort_by = "score"
		query = query.order_by(db.desc(Package.score))

	return render_template("todo/outdated.html", current_tab="outdated",
			outdated_packages=query.all(), sort_by=sort_by, is_mtm_only=is_mtm_only)


@bp.route("/todo/screenshots/")
@login_required
def screenshots():
	is_mtm_only = is_yes(request.args.get("mtm"))

	query = db.session.query(Package) \
			.filter(~Package.screenshots.any()) \
			.filter(Package.state == PackageState.APPROVED)

	if is_mtm_only:
		query = query.filter(Package.repo.ilike("%github.com/minetest-mods/%"))

	sort_by = request.args.get("sort")
	if sort_by == "date":
		query = query.order_by(db.desc(Package.approved_at))
	else:
		sort_by = "score"
		query = query.order_by(db.desc(Package.score))

	return render_template("todo/screenshots.html", current_tab="screenshots",
			packages=query.all(), sort_by=sort_by, is_mtm_only=is_mtm_only)


@bp.route("/todo/mtver_support/")
@login_required
def mtver_support():
	is_mtm_only = is_yes(request.args.get("mtm"))

	current_stable = LuantiRelease.query.filter(~LuantiRelease.name.like("%-dev")).order_by(db.desc(LuantiRelease.id)).first()

	query = db.session.query(Package) \
			.filter(~Package.releases.any(or_(PackageRelease.max_rel==None, PackageRelease.max_rel == current_stable))) \
			.filter(Package.state == PackageState.APPROVED)

	if is_mtm_only:
		query = query.filter(Package.repo.ilike("%github.com/minetest-mods/%"))

	sort_by = request.args.get("sort")
	if sort_by == "date":
		query = query.order_by(db.desc(Package.approved_at))
	else:
		sort_by = "score"
		query = query.order_by(db.desc(Package.score))

	return render_template("todo/mtver_support.html", current_tab="screenshots",
			packages=query.all(), sort_by=sort_by, is_mtm_only=is_mtm_only, current_stable=current_stable)


@bp.route("/todo/topics/mismatch/")
@rank_required(UserRank.EDITOR)
def topics_mismatch():
	missing_topics = Package.query.filter(Package.forums.is_not(None)) .filter(~ForumTopic.query.filter(ForumTopic.topic_id == Package.forums).exists()).all()

	packages_bad_author = (
		db.session.query(Package, ForumTopic)
		.select_from(Package)
		.join(ForumTopic, Package.forums == ForumTopic.topic_id)
		.filter(Package.author_id != ForumTopic.author_id)
		.all())

	packages_bad_title = (
		db.session.query(Package, ForumTopic)
		.select_from(Package)
		.join(ForumTopic, Package.forums == ForumTopic.topic_id)
		.filter(and_(ForumTopic.name != Package.name, ~ForumTopic.title.ilike("%" + Package.title + "%"), ~ForumTopic.title.ilike("%" + Package.name + "%")))
		.all())

	return render_template("todo/topics_mismatch.html",
			missing_topics=missing_topics,
			packages_bad_author=packages_bad_author,
			packages_bad_title=packages_bad_title)
