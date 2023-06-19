# ContentDB
# Copyright (C) 2018-21 rubenwardy
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

import datetime
import re

from celery import uuid
from flask_babel import lazy_gettext

from app.logic.LogicError import LogicError
from app.logic.uploads import upload_file
from app.models import PackageRelease, db, Permission, User, Package, MinetestRelease
from app.tasks.importtasks import make_vcs_release, check_zip_release
from app.utils import AuditSeverity, add_audit_log, nonempty_or_none


def check_can_create_release(user: User, package: Package):
	if not package.check_perm(user, Permission.MAKE_RELEASE):
		raise LogicError(403, lazy_gettext("You don't have permission to make releases"))

	five_minutes_ago = datetime.datetime.now() - datetime.timedelta(minutes=5)
	count = package.releases.filter(PackageRelease.releaseDate > five_minutes_ago).count()
	if count >= 5:
		raise LogicError(429, lazy_gettext("You've created too many releases for this package in the last 5 minutes, please wait before trying again"))


def do_create_vcs_release(user: User, package: Package, title: str, ref: str,
		min_v: MinetestRelease = None, max_v: MinetestRelease = None, reason: str = None):
	check_can_create_release(user, package)

	rel = PackageRelease()
	rel.package = package
	rel.title   = title
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


def do_create_zip_release(user: User, package: Package, title: str, file,
		min_v: MinetestRelease = None, max_v: MinetestRelease = None, reason: str = None,
		commit_hash: str = None):
	check_can_create_release(user, package)

	if commit_hash:
		commit_hash = commit_hash.lower()
		if not (len(commit_hash) == 40 and re.match(r"^[0-9a-f]+$", commit_hash)):
			raise LogicError(400, lazy_gettext("Invalid commit hash; it must be a 40 character long base16 string"))

	uploaded_url, uploaded_path = upload_file(file, "zip", "a zip file")

	rel = PackageRelease()
	rel.package = package
	rel.title   = title
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
