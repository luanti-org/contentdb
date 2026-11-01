# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import enum
from typing import Optional
from urllib.parse import urlsplit

from app import app
from app.models import User, UserRank, Package


class GitAccess(enum.Enum):
	# No git features for anyone
	NONE = "none"

	# Only trusted members, and packages by trusted members
	TRUSTED = "trusted"

	# As TRUSTED, plus approved packages. Anyone with permission may use git features on an approved package
	TRUSTED_OR_APPROVED = "trusted_or_approved"

	# Everyone
	ALL = "all"


def get_git_access() -> GitAccess:
	return GitAccess(app.config.get("GIT_ACCESS", GitAccess.NONE.value))


def _is_trusted(user: Optional[User]) -> bool:
	return user is not None and user.rank.at_least(UserRank.TRUSTED_MEMBER)


def can_user_use_git(user: Optional[User]) -> bool:
	"""
	Whether a user may use git features that aren't tied to a package, such as importing metadata from a repo
	"""
	access = get_git_access()
	if access == GitAccess.ALL:
		return True
	elif access in (GitAccess.TRUSTED, GitAccess.TRUSTED_OR_APPROVED):
		return _is_trusted(user)
	else:
		return False


def can_package_use_git(package: Package) -> bool:
	"""
	Whether git features may be used on this package. This depends on the package's author, not the user performing
	the action, so all maintainers have the same access.
	"""
	access = get_git_access()
	if access == GitAccess.ALL:
		return True
	elif access == GitAccess.TRUSTED_OR_APPROVED and package.approved:
		return True
	elif access in (GitAccess.TRUSTED, GitAccess.TRUSTED_OR_APPROVED):
		return _is_trusted(package.author)
	else:
		return False


def normalize_repo_url(url: Optional[str]) -> Optional[str]:
	"""
	Reduces a repo URL to the parts that identify the repo. The scheme, a trailing slash, and a trailing .git are
	ignored, and the host is lowercased. The path keeps its case, as some hosts are case-sensitive.
	"""
	if url is None:
		return None

	parts = urlsplit(url.strip())
	path = parts.path.rstrip("/")
	if path.endswith(".git"):
		path = path[:-4].rstrip("/")

	query = "?" + parts.query if parts.query else ""
	return parts.netloc.lower() + path + query


def is_same_repo(a: Optional[str], b: Optional[str]) -> bool:
	return normalize_repo_url(a) == normalize_repo_url(b)


def can_user_change_repo(user: Optional[User], package: Package) -> bool:
	"""
	The caller is responsible for also checking for EDIT_PACKAGE

	:param user: The user making the change, or None if unknown. An unknown user is treated as untrusted.
	"""
	if get_git_access() == GitAccess.ALL:
		return True

	is_vetted = _is_trusted(package.author) or package.approved
	return not is_vetted or _is_trusted(user)
