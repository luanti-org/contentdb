# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Helpers for permission table tests.

A table maps each permission to the set of roles that should have it. Every other role must be denied, so the
tables also show what each role can't do. `assert_permissions` reports all mismatches at once.
"""

from typing import Any, Iterable

from flask_login import AnonymousUserMixin

from app.models import UserRank, Package, Permission
from .factories import create_user, create_package


# Roles relative to a package. "maintainer" and "banned" are maintainers of the package as well as "owner".
PACKAGE_ROLES = ["anonymous", "banned", "new_member", "member", "trusted", "maintainer", "owner",
		"approver", "editor", "moderator", "admin"]


def make_roles(ranks: dict[str, UserRank | None]) -> dict[str, Any]:
	"""
	Creates a user for each role, named after the role. A rank of None means an anonymous user.
	"""
	return {name: AnonymousUserMixin() if rank is None else create_user(name, rank) for name, rank in ranks.items()}


def make_package_roles(**package_args) -> tuple[Package, dict[str, Any]]:
	"""
	Creates a package owned by "owner", maintained by "maintainer" and "banned", and a user for each other role.
	"""
	owner = create_user("owner", UserRank.MEMBER)
	maintainer = create_user("maintainer", UserRank.MEMBER)
	banned = create_user("banned", UserRank.BANNED)
	package = create_package("pkg", owner, maintainers=[maintainer, banned], **package_args)

	roles: dict[str, Any] = {
		"anonymous": AnonymousUserMixin(),
		"banned": banned,
		"new_member": create_user("new_member", UserRank.NEW_MEMBER),
		"member": create_user("member", UserRank.MEMBER),
		"trusted": create_user("trusted", UserRank.TRUSTED_MEMBER),
		"maintainer": maintainer,
		"owner": owner,
		"approver": create_user("approver", UserRank.APPROVER),
		"editor": create_user("editor", UserRank.EDITOR),
		"moderator": create_user("moderator", UserRank.MODERATOR),
		"admin": create_user("admin", UserRank.ADMIN),
	}
	return package, roles


def assert_permissions(obj: Any, roles: dict[str, Any], table: dict[Permission, Iterable[str]], label: str = ""):
	"""
	Checks `obj.check_perm(user, perm)` for every role and permission in `table`. Roles in the table's set must be
	allowed, and every other role denied.
	"""
	unknown = {role for allowed in table.values() for role in allowed} - set(roles)
	assert not unknown, f"Unknown roles in table: {unknown}"

	mismatches = []
	for perm, allowed in table.items():
		allowed = set(allowed)
		for role, user in roles.items():
			actual = obj.check_perm(user, perm)
			expected = role in allowed
			if actual != expected:
				mismatches.append(f"{perm.name} for {role}: expected {expected}, got {actual}")

	assert not mismatches, f"Permission mismatches{' (' + label + ')' if label else ''}:\n" + "\n".join(mismatches)


def everyone_except(*excluded: str, roles: Iterable[str] = PACKAGE_ROLES) -> set[str]:
	return set(roles) - set(excluded)
