# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Permission tables for `User.check_perm`, for permissions acting on a target user. See permission_tables.py.
Renaming and profile editing are covered by test_user_permissions.py.
"""

import pytest

from app.models import UserRank, Permission
from ..factories import create_user
from ..permission_tables import make_roles, assert_permissions


MEMBERS_AND_ABOVE = {"member", "trusted", "approver", "editor", "moderator", "admin"}


def make_user_roles(target_rank: UserRank):
	roles = make_roles({
		"anonymous": None,
		"new_member": UserRank.NEW_MEMBER,
		"member": UserRank.MEMBER,
		"trusted": UserRank.TRUSTED_MEMBER,
		"approver": UserRank.APPROVER,
		"editor": UserRank.EDITOR,
		"moderator": UserRank.MODERATOR,
		"admin": UserRank.ADMIN,
	})
	roles["self"] = create_user("target", target_rank)
	return roles["self"], roles


# link_to_website depends only on the acting user's rank, so includes "self" for members and above
@pytest.mark.parametrize("target_rank,managers,link_to_website", [
	(UserRank.BANNED, {"moderator", "admin"}, MEMBERS_AND_ABOVE),
	(UserRank.NEW_MEMBER, {"moderator", "admin"}, MEMBERS_AND_ABOVE),
	(UserRank.MEMBER, {"moderator", "admin"}, MEMBERS_AND_ABOVE | {"self"}),
	(UserRank.EDITOR, {"moderator", "admin"}, MEMBERS_AND_ABOVE | {"self"}),
	# Staff can only manage users ranked below them
	(UserRank.MODERATOR, {"admin"}, MEMBERS_AND_ABOVE | {"self"}),
	(UserRank.ADMIN, set(), MEMBERS_AND_ABOVE | {"self"}),
])
def test_user(client, target_rank, managers, link_to_website):
	target, roles = make_user_roles(target_rank)

	# CHANGE_AUTHOR depends only on the acting user's rank, not on the target
	editors = {"editor", "moderator", "admin"} | ({"self"} if target_rank.at_least(UserRank.EDITOR) else set())

	# Banned users can't create tokens or apps for themselves
	self_service = {"self"} if target_rank.at_least(UserRank.NEW_MEMBER) else set()

	assert_permissions(target, roles, {
		Permission.CHANGE_AUTHOR: editors,
		Permission.CHANGE_RANK: managers,
		Permission.CHANGE_EMAIL: {"self"} | managers,
		Permission.CHANGE_PROFILE_URLS: {"self"} | managers,
		Permission.CREATE_TOKEN: self_service | managers,
		Permission.CREATE_OAUTH_CLIENT: self_service | managers,
		Permission.LINK_TO_WEBSITE: link_to_website,
	})
