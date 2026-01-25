# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import re
from typing import Optional

from celery import uuid
from flask_babel import lazy_gettext

from app.logic.LogicError import LogicError
from app.logic.uploads import upload_file
from app.models import PackageRelease, db, Permission, User, Package, LuantiRelease, AuditSeverity
from app.tasks.importtasks import make_vcs_release, check_zip_release
from app.utils.models import add_audit_log
from app.utils.misc import nonempty_or_none, normalize_line_endings


def check_can_create_release(user: User, package: Package, name: str):
	if not package.check_perm(user, Permission.MAKE_RELEASE):
		raise LogicError(403, lazy_gettext("You don't have permission to make releases"))

	five_minutes_ago = datetime.datetime.now() - datetime.timedelta(minutes=5)
	count = package.releases.filter(PackageRelease.created_at > five_minutes_ago).count()
	if count >= 5:
		raise LogicError(429, lazy_gettext("You've created too many releases for this package in the last 5 minutes, please wait before trying again"))

	if PackageRelease.query.filter_by(package_id=package.id, name=name).count() > 0:
		raise LogicError(403, lazy_gettext("A release with this name already exists"))


def do_create_vcs_release(user: User, package: Package, name: str, title: Optional[str], release_notes: Optional[str], ref: str,
		min_v: LuantiRelease = None, max_v: LuantiRelease = None, reason: str = None):
	check_can_create_release(user, package, name)

	rel = PackageRelease()
	rel.package = package
	rel.name    = name
	rel.title   = title or name
	rel.release_notes = normalize_line_endings(release_notes)
	rel.url     = ""
	rel.task_id = uuid()
	rel.min_rel = min_v
	rel.max_rel = max_v
	db.session.add(rel)

	if reason is None:
		msg = "Created release {}".format(rel.title)
	else:
		msg = "Created release {} ({})".format(rel.title, reason)
	add_audit_log(AuditSeverity.NORMAL, user, msg, package.get_url("packages.view"), package)

	db.session.commit()

	make_vcs_release.apply_async((rel.id, nonempty_or_none(ref)), task_id=rel.task_id)

	return rel


def do_create_zip_release(user: User, package: Package, name: str, title: Optional[str], release_notes: Optional[str], file,
		min_v: LuantiRelease = None, max_v: LuantiRelease = None, reason: str = None,
		commit_hash: str = None):
	check_can_create_release(user, package, name)

	if commit_hash:
		commit_hash = commit_hash.lower()
		if not (len(commit_hash) == 40 and re.match(r"^[0-9a-f]+$", commit_hash)):
			raise LogicError(400, lazy_gettext("Invalid commit hash; it must be a 40 character long base16 string"))

	uploaded_url, uploaded_path = upload_file(file, "zip", "a zip file")

	rel = PackageRelease()
	rel.package = package
	rel.name    = name
	rel.title   = title or name
	rel.release_notes = normalize_line_endings(release_notes)
	rel.url     = uploaded_url
	rel.task_id = uuid()
	rel.commit_hash = commit_hash
	rel.min_rel = min_v
	rel.max_rel = max_v
	db.session.add(rel)

	if reason is None:
		msg = "Created release {}".format(rel.title)
	else:
		msg = "Created release {} ({})".format(rel.title, reason)
	add_audit_log(AuditSeverity.NORMAL, user, msg, package.get_url("packages.view"), package)

	db.session.commit()

	check_zip_release.apply_async((rel.id, uploaded_path), task_id=rel.task_id)

	return rel
