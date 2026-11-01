# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import pytest

from app.models import db, User, UserRank, Permission
from app.utils.user import make_flask_login_password
from .utils import login
from .utils import client # noqa


PASSWORD = "VYjNnjdDPhCVUZx"


def make_user(username: str, rank: UserRank) -> User:
	user = User(username, active=True, email=f"{username}@example.com",
			password=make_flask_login_password(PASSWORD))
	user.rank = rank
	user.github_username = f"{username}_gh"
	db.session.add(user)
	return user


@pytest.mark.parametrize("perm", [Permission.CHANGE_USERNAMES, Permission.CHANGE_DISPLAY_NAME])
@pytest.mark.parametrize("actor_rank,target_rank,expected", [
	(UserRank.MODERATOR, UserRank.MEMBER, True),
	(UserRank.MODERATOR, UserRank.EDITOR, True),
	(UserRank.MODERATOR, UserRank.MODERATOR, False),
	(UserRank.MODERATOR, UserRank.ADMIN, False),
	(UserRank.ADMIN, UserRank.MODERATOR, True),
	(UserRank.ADMIN, UserRank.ADMIN, False),
	(UserRank.EDITOR, UserRank.MEMBER, False),
])
def test_rename_permission_for_other_users(client, perm, actor_rank, target_rank, expected):
	actor = make_user("actor", actor_rank)
	target = make_user("target", target_rank)
	db.session.commit()

	assert target.check_perm(actor, perm) == expected


@pytest.mark.parametrize("actor_rank,target_rank,expected", [
	(UserRank.MODERATOR, UserRank.MEMBER, True),
	(UserRank.MODERATOR, UserRank.MODERATOR, False),
	(UserRank.MODERATOR, UserRank.ADMIN, False),
	(UserRank.ADMIN, UserRank.MODERATOR, True),
	(UserRank.EDITOR, UserRank.MEMBER, False),
])
def test_can_see_edit_profile(client, actor_rank, target_rank, expected):
	actor = make_user("actor", actor_rank)
	target = make_user("target", target_rank)
	db.session.commit()

	assert target.can_see_edit_profile(actor) == expected


@pytest.mark.parametrize("rank,can_rename_self", [
	(UserRank.NEW_MEMBER, False),
	(UserRank.MODERATOR, True),
	(UserRank.ADMIN, True),
])
def test_rename_permission_for_self(client, rank, can_rename_self):
	user = make_user("actor", rank)
	db.session.commit()

	assert user.check_perm(user, Permission.CHANGE_DISPLAY_NAME)
	assert user.check_perm(user, Permission.CHANGE_USERNAMES) == can_rename_self
	assert user.can_see_edit_profile(user)


@pytest.mark.parametrize("target_rank,allowed", [
	(UserRank.MEMBER, True),
	(UserRank.MODERATOR, False),
	(UserRank.ADMIN, False),
])
def test_moderator_edit_other_profile(client, target_rank, allowed):
	make_user("moderator", UserRank.MODERATOR)
	make_user("target", target_rank)
	db.session.commit()

	login(client, "moderator", PASSWORD)

	expected_status = 200 if allowed else 403
	assert client.get("/users/target/settings/profile/").status_code == expected_status
	assert client.get("/users/target/settings/account/").status_code == expected_status

	rv = client.post("/users/target/settings/profile/", data=dict(display_name="Renamed"))
	assert rv.status_code == (302 if allowed else 403)

	rv = client.post("/users/target/settings/account/disconnect-github/")
	assert rv.status_code == (302 if allowed else 403)

	target = User.query.filter_by(username="target").one()
	assert target.display_name == ("Renamed" if allowed else "target")
	assert target.github_username == (None if allowed else "target_gh")
