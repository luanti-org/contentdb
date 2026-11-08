# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import re
from typing import List, Optional, Tuple

from celery import uuid
from flask_babel import lazy_gettext

from app.domain.DomainError import DomainError
from app.uploads import upload_file
from app.models import PackageRelease, db, Permission, User, Package, LuantiRelease, AuditSeverity, UserRank
from app.tasks.importtasks import make_vcs_release, check_zip_release
from app.domain.git_access import can_package_use_git
from app.utils.models import add_audit_log
from app.utils.ratelimit import RateLimit
from app.utils.misc import nonempty_or_none, normalize_line_endings


def check_can_create_release(user: User, package: Package, name: str, title: str) -> List[RateLimit]:
	"""
	Throws `DomainError` if the release can't be created. Returns the rate limits to record once it has been created.
	"""
	if not package.check_perm(user, Permission.MAKE_RELEASE):
		raise DomainError(403, lazy_gettext("You don't have permission to make releases"))

	if PackageRelease.query.filter_by(package_id=package.id, name=name).count() > 0:
		raise DomainError(403, lazy_gettext("A release with this name already exists"))

	if PackageRelease.query.filter_by(package_id=package.id, title=title).count() > 0:
		raise DomainError(403, lazy_gettext("A release with this title already exists"))

	release_name_re = re.compile(r"^[A-Za-z]*\.?\d+([.\-/][\dA-Za-z]+)*$")
	if not release_name_re.match(name):
		raise DomainError(403, lazy_gettext("Release name must be in the form 1.2.3, v1.2.3, or 2025-02-01"))

	# Only checked here. They're recorded once the release has been created, so rejected requests don't use them up
	package_limit = RateLimit(f"release/package:{package.id}", ["7 per 5 minutes"])
	if not package_limit.test():
		raise DomainError(429, lazy_gettext("You've created too many releases for this package in the last 5 minutes, please wait before trying again"))

	user_limit = RateLimit(f"release/user:{user.id}", [] if user.rank.at_least(UserRank.TRUSTED_MEMBER) else ["30 per hour"])
	if not user_limit.test():
		raise DomainError(429, lazy_gettext("You've created too many releases in the last hour, please wait before trying again"))

	return [package_limit, user_limit]


def _record_release(limits: List[RateLimit]):
	"""
	Records a release against the limits from `check_can_create_release`, once it has been created
	"""
	for limit in limits:
		limit.record()


def do_create_vcs_release(user: User, package: Package, name: str, title: Optional[str], release_notes: Optional[str], ref: Optional[str],
		min_v: LuantiRelease | None = None, max_v: LuantiRelease | None = None,
		reason: str | None = None) -> Tuple[PackageRelease, str]:
	"""
	Returns the release and the ID of the task that imports it. Use the returned ID rather than `release.task_id`,
	which the task clears when it finishes, possibly before this returns.
	"""
	if not can_package_use_git(package):
		raise DomainError(503, lazy_gettext("Creating releases from Git is temporarily disabled, please upload a .zip file instead"))

	limits = check_can_create_release(user, package, name, title or name)

	rel = PackageRelease()
	rel.package = package
	rel.name    = name
	rel.title   = title or name
	rel.release_notes = normalize_line_endings(release_notes)
	rel.upload_path = ""
	task_id = rel.task_id = uuid()
	rel.min_rel = min_v
	rel.max_rel = max_v
	db.session.add(rel)

	if reason is None:
		msg = "Created release {}".format(rel.title)
	else:
		msg = "Created release {} ({})".format(rel.title, reason)
	add_audit_log(AuditSeverity.NORMAL, user, msg, package.get_url("packages.view"), package)

	db.session.commit()
	_record_release(limits)

	ref = nonempty_or_none(ref)
	if ref:
		ref = ref.strip()

	make_vcs_release.apply_async((rel.id, ref), task_id=task_id)

	return rel, task_id


def do_create_zip_release(user: User, package: Package, name: str, title: Optional[str], release_notes: Optional[str], file,
		min_v: LuantiRelease | None = None, max_v: LuantiRelease | None = None, reason: str | None = None,
		commit_hash: str | None = None) -> Tuple[PackageRelease, str]:
	"""
	Returns the release and the ID of the task that checks it. Use the returned ID rather than `release.task_id`,
	which the task clears when it finishes, possibly before this returns.
	"""
	limits = check_can_create_release(user, package, name, title or name)

	if commit_hash:
		commit_hash = commit_hash.lower()
		if not (len(commit_hash) == 40 and re.match(r"^[0-9a-f]+$", commit_hash)):
			raise DomainError(400, lazy_gettext("Invalid commit hash; it must be a 40 character long base16 string"))

	uploaded_url, _ = upload_file(file, "zip", "a zip file")

	rel = PackageRelease()
	rel.package = package
	rel.name    = name
	rel.title   = title or name
	rel.release_notes = normalize_line_endings(release_notes)
	rel.upload_path     = uploaded_url
	task_id = rel.task_id = uuid()
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
	_record_release(limits)

	check_zip_release.apply_async((rel.id,), task_id=task_id)

	return rel, task_id
