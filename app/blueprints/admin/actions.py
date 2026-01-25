# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import os
from typing import List

import requests
from celery import group, uuid
from flask import redirect, url_for, flash, current_app
from sqlalchemy import or_, and_, not_, func
from flask_login import current_user

from app.models import PackageRelease, db, Package, PackageState, PackageScreenshot, MetaPackage, User, \
	NotificationType, PackageUpdateConfig, License, UserRank, PackageType, Thread, AuditLogEntry, ReportAttachment, \
	PackageAIDisclosure, AuditSeverity
from app.tasks.admintasks import delete_empty_threads
from app.tasks.emails import send_pending_digests
from app.tasks.forumtasks import import_topic_list, check_all_forum_accounts
from app.tasks.importtasks import import_repo_screenshot, check_zip_release, check_for_updates, update_all_game_support, \
	import_languages, check_all_zip_files
from app.tasks.usertasks import import_github_user_ids
from app.tasks.pkgtasks import notify_about_git_forum_links, clear_removed_packages, check_package_for_broken_links, update_file_size_bytes
from app.utils.models import add_notification, get_system_user, add_audit_log

actions = {}


def action(title: str):
	def func(f):
		name = f.__name__
		actions[name] = {
			"title": title,
			"func": f,
		}

		return f

	return func


@action("Delete stuck releases")
def del_stuck_releases():
	PackageRelease.query.filter(PackageRelease.task_id.isnot(None)).delete()
	db.session.commit()
	return redirect(url_for("admin.admin_page"))

@action("Delete unused uploads")
def clean_uploads():
	upload_dir = current_app.config['UPLOAD_DIR']

	(_, _, filenames) = next(os.walk(upload_dir))
	existing_uploads = set(filenames)

	if len(existing_uploads) != 0:
		def get_filenames_from_column(column):
			results = db.session.query(column).filter(column.isnot(None), column != "").all()
			return set([os.path.basename(x[0]) for x in results])

		release_urls = get_filenames_from_column(PackageRelease.url)
		screenshot_urls = get_filenames_from_column(PackageScreenshot.url)
		attachment_urls = get_filenames_from_column(ReportAttachment.url)
		pp_urls = get_filenames_from_column(User.profile_pic)

		db_urls = release_urls.union(screenshot_urls).union(pp_urls).union(attachment_urls)
		unreachable = existing_uploads.difference(db_urls)

		import sys
		print("On Disk: ", existing_uploads, file=sys.stderr)
		print("In DB: ", db_urls, file=sys.stderr)
		print("Unreachable: ", unreachable, file=sys.stderr)

		for filename in unreachable:
			os.remove(os.path.join(upload_dir, filename))

		flash("Deleted " + str(len(unreachable)) + " unreachable uploads", "success")
	else:
		flash("No downloads to create", "danger")

	return redirect(url_for("admin.admin_page"))


@action("Delete unused mod names")
def del_mod_names():
	query = MetaPackage.query.filter(~MetaPackage.dependencies.any(), ~MetaPackage.packages.any())
	count = query.count()
	query.delete(synchronize_session=False)
	db.session.commit()

	flash("Deleted " + str(count) + " unused mod names", "success")
	return redirect(url_for("admin.admin_page"))


@action("Recalc package scores")
def recalc_scores():
	for package in Package.query.all():
		package.recalculate_score()

	db.session.commit()

	flash("Recalculated package scores", "success")
	return redirect(url_for("admin.admin_page"))


@action("Import forum topic list")
def do_import_topic_list():
	task = import_topic_list.delay()
	return redirect(url_for("tasks.check", id=task.id, r=url_for("admin.admin_page")))


@action("Check all forum accounts")
def check_all_forum_accounts():
	task = check_all_forum_accounts.delay()
	return redirect(url_for("tasks.check", id=task.id, r=url_for("admin.admin_page")))


@action("Run update configs")
def run_update_config():
	check_for_updates.delay()

	flash("Started update configs", "success")
	return redirect(url_for("admin.admin_page"))


def _package_list(packages: List[str]):
	# Who needs translations?
	if len(packages) >= 3:
		packages[len(packages) - 1] = "and " + packages[len(packages) - 1]
		return ", ".join(packages)
	else:
		return " and ".join(packages)


@action("Send WIP package notification")
def remind_wip():
	users = User.query.filter(User.packages.any(or_(
			Package.state == PackageState.WIP, Package.state == PackageState.CHANGES_NEEDED)))
	system_user = get_system_user()
	for user in users:
		packages = Package.query.filter(
				Package.author_id == user.id,
				or_(Package.state == PackageState.WIP, Package.state == PackageState.CHANGES_NEEDED)) \
			.all()

		packages = [pkg.title for pkg in packages]
		packages_list = _package_list(packages)
		havent = "haven't" if len(packages) > 1 else "hasn't"

		add_notification(user, system_user, NotificationType.PACKAGE_APPROVAL,
			f"Did you forget? {packages_list} {havent} been submitted for review yet",
						 url_for('todo.view_user', username=user.username))
	db.session.commit()


@action("Send outdated package notification")
def remind_outdated():
	users = User.query.filter(User.maintained_packages.any(
			Package.update_config.has(PackageUpdateConfig.outdated_at.isnot(None))))
	system_user = get_system_user()
	for user in users:
		packages = Package.query.filter(
				Package.maintainers.contains(user),
				Package.update_config.has(PackageUpdateConfig.outdated_at.isnot(None))) \
			.all()

		packages = [pkg.title for pkg in packages]
		packages_list = _package_list(packages)

		add_notification(user, system_user, NotificationType.PACKAGE_APPROVAL,
				f"The following packages may be outdated: {packages_list}",
						 url_for('todo.view_user', username=user.username))

	db.session.commit()


@action("Import licenses from SPDX")
def import_licenses():
	renames = {
		"GPLv2": "GPL-2.0-only",
		"GPLv3": "GPL-3.0-only",
		"AGPLv2": "AGPL-2.0-only",
		"AGPLv3": "AGPL-3.0-only",
		"LGPLv2.1": "LGPL-2.1-only",
		"LGPLv3": "LGPL-3.0-only",
		"Apache 2.0": "Apache-2.0",
		"BSD 2-Clause / FreeBSD": "BSD-2-Clause-FreeBSD",
		"BSD 3-Clause": "BSD-3-Clause",
		"CC0": "CC0-1.0",
		"CC BY 3.0": "CC-BY-3.0",
		"CC BY 4.0": "CC-BY-4.0",
		"CC BY-NC-SA 3.0": "CC-BY-NC-SA-3.0",
		"CC BY-SA 3.0": "CC-BY-SA-3.0",
		"CC BY-SA 4.0": "CC-BY-SA-4.0",
		"NPOSLv3": "NPOSL-3.0",
		"MPL 2.0": "MPL-2.0",
		"EUPLv1.2": "EUPL-1.2",
		"SIL Open Font License v1.1": "OFL-1.1",
	}

	for old_name, new_name in renames.items():
		License.query.filter_by(name=old_name).update({ "name": new_name })

	r = requests.get(
			"https://raw.githubusercontent.com/spdx/license-list-data/master/json/licenses.json")
	licenses = r.json()["licenses"]

	existing_licenses = {}
	for license_data in License.query.all():
		assert license_data.name not in renames.keys()
		existing_licenses[license_data.name.lower()] = license_data

	for license_data in licenses:
		obj = existing_licenses.get(license_data["licenseId"].lower())
		if obj:
			obj.url = license_data["reference"]
		elif license_data.get("isOsiApproved") and license_data.get("isFsfLibre") and not license_data["isDeprecatedLicenseId"]:
			obj = License(license_data["licenseId"], True, license_data["reference"])
			db.session.add(obj)

	db.session.commit()


@action("Delete inactive users")
def delete_inactive_users():
	users = User.query.filter(User.is_active == False, ~User.packages.any(), ~User.forum_topics.any(),
			User.rank == UserRank.NOT_JOINED).all()
	for user in users:
		db.session.delete(user)
	db.session.commit()


@action("Send Video URL notification")
def remind_video_url():
	users = User.query.filter(User.maintained_packages.any(
			and_(Package.video_url == None, Package.type == PackageType.GAME, Package.state == PackageState.APPROVED)))
	system_user = get_system_user()
	for user in users:
		packages = Package.query.filter(
				or_(Package.author == user, Package.maintainers.contains(user)),
				Package.video_url == None,
				Package.type == PackageType.GAME,
				Package.state == PackageState.APPROVED) \
			.all()

		package_names = [pkg.title for pkg in packages]
		packages_list = _package_list(package_names)

		add_notification(user, system_user, NotificationType.PACKAGE_APPROVAL,
				f"You should add a video to {packages_list}",
						 url_for('users.profile', username=user.username))

	db.session.commit()


@action("Send missing game support notifications")
def remind_missing_game_support():
	users = User.query.filter(
		User.maintained_packages.any(and_(
			Package.state != PackageState.DELETED,
			Package.type.in_([PackageType.MOD, PackageType.TXP]),
			~Package.supported_games.any(),
			Package.supports_all_games == False))).all()

	system_user = get_system_user()
	for user in users:
		packages = Package.query.filter(
			Package.maintainers.contains(user),
			Package.state != PackageState.DELETED,
			Package.type.in_([PackageType.MOD, PackageType.TXP]),
			~Package.supported_games.any(),
			Package.supports_all_games == False) \
			.all()

		packages = [pkg.title for pkg in packages]
		packages_list = _package_list(packages)

		add_notification(user, system_user, NotificationType.PACKAGE_APPROVAL,
				f"You need to confirm whether the following packages support all games: {packages_list}",
				url_for('todo.all_game_support', username=user.username))

	db.session.commit()


@action("Detect game support")
def detect_game_support():
	task_id = uuid()
	update_all_game_support.apply_async((), task_id=task_id)
	return redirect(url_for("tasks.check", id=task_id, r=url_for("admin.admin_page")))


@action("Send pending notif digests")
def do_send_pending_digests():
	send_pending_digests.delay()


@action("Import user ids from GitHub")
def do_import_github_user_ids():
	task_id = uuid()
	import_github_user_ids.apply_async((), task_id=task_id)
	return redirect(url_for("tasks.check", id=task_id, r=url_for("admin.admin_page")))


@action("Notify about links to git/forums instead of CDB")
def do_notify_git_forums_links():
	task_id = uuid()
	notify_about_git_forum_links.apply_async((), task_id=task_id)
	return redirect(url_for("tasks.check", id=task_id, r=url_for("admin.admin_page")))


@action("Check all zip files")
def do_check_all_zip_files():
	task_id = uuid()
	check_all_zip_files.apply_async((), task_id=task_id)
	return redirect(url_for("tasks.check", id=task_id, r=url_for("admin.admin_page")))


@action("Update file_size_bytes")
def do_update_file_size_bytes():
	task_id = uuid()
	update_file_size_bytes.apply_async((), task_id=task_id)
	return redirect(url_for("tasks.check", id=task_id, r=url_for("admin.admin_page")))


@action("DANGER: Delete less popular removed packages")
def del_less_popular_removed_packages():
	task_id = uuid()
	clear_removed_packages.apply_async((False, ), task_id=task_id)
	return redirect(url_for("tasks.check", id=task_id, r=url_for("admin.admin_page")))


@action("DANGER: Delete all removed packages")
def del_removed_packages():
	task_id = uuid()
	clear_removed_packages.apply_async((True, ), task_id=task_id)
	return redirect(url_for("tasks.check", id=task_id, r=url_for("admin.admin_page")))


@action("DANGER: Check all releases (postReleaseCheckUpdate)")
def check_releases():
	releases = PackageRelease.query.filter(PackageRelease.url.like("/uploads/%")).all()

	tasks = []
	for release in releases:
		tasks.append(check_zip_release.s(release.id, release.file_path))

	result = group(tasks).apply_async()

	while not result.ready():
		import time
		time.sleep(0.1)

	return redirect(url_for("todo.view_editor"))


@action("DANGER: Check latest release of all packages (postReleaseCheckUpdate)")
def reimport_packages():
	tasks = []
	for package in Package.query.filter(Package.state == PackageState.APPROVED).all():
		release = package.releases.first()
		if release:
			tasks.append(check_zip_release.s(release.id, release.file_path))

	result = group(tasks).apply_async()

	while not result.ready():
		import time
		time.sleep(0.1)

	return redirect(url_for("todo.view_editor"))


@action("DANGER: Import translations")
def reimport_translations():
	tasks = []
	for package in Package.query.filter(Package.state == PackageState.APPROVED).all():
		release = package.releases.first()
		if release:
			tasks.append(import_languages.s(release.id, release.file_path))

	result = group(tasks).apply_async()
	while not result.ready():
		import time
		time.sleep(0.1)

	return redirect(url_for("todo.view_editor"))


@action("DANGER: Import screenshots from Git")
def import_screenshots():
	packages = Package.query \
		.filter(Package.state != PackageState.DELETED) \
		.outerjoin(PackageScreenshot, Package.id == PackageScreenshot.package_id) \
		.filter(PackageScreenshot.id == None) \
		.all()
	for package in packages:
		import_repo_screenshot.delay(package.id)

	return redirect(url_for("admin.admin_page"))


@action("DANGER: Delete empty threads")
def do_delete_empty_threads():
	delete_empty_threads.delay()
	return redirect(url_for("admin.admin_page"))


@action("DANGER: Check for broken links in all packages")
def check_for_broken_links():
	for package in Package.query.filter_by(state=PackageState.APPROVED).all():
		check_package_for_broken_links.delay(package.id)


@action("DANGER: Update AI disclosure for old packages")
def old_package_ai_disclosure():
	cutoff = datetime.date(2022, 3, 1)
	stmt = (
		db.session.query(Package)
		.filter(
			~Package.releases.any(PackageRelease.created_at > cutoff),
			Package.ai_disclosure == PackageAIDisclosure.UNKNOWN,
		)
		.all()
	)
	for package in stmt:
		package.ai_disclosure = PackageAIDisclosure.NONE
		add_audit_log(AuditSeverity.NORMAL, current_user, f"Set AI disclosure to None", package.get_url("packages.view"), package)

	return redirect(url_for("admin.admin_page"))
