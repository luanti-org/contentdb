# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import pytest

from app.models import db, User, UserRank, APIToken, Permission
from app.utils.user import make_flask_login_password
from .utils import login
from .utils import client # noqa


PASSWORD = "VYjNnjdDPhCVUZx"


def make_user(username: str, rank: UserRank) -> User:
	user = User(username, active=True, email=f"{username}@example.com",
			password=make_flask_login_password(PASSWORD))
	user.rank = rank
	db.session.add(user)
	return user


@pytest.mark.parametrize("perm", [Permission.CREATE_TOKEN, Permission.CREATE_OAUTH_CLIENT])
@pytest.mark.parametrize("actor_rank,target_rank,expected", [
	(UserRank.MODERATOR, UserRank.MEMBER, True),
	(UserRank.MODERATOR, UserRank.EDITOR, True),
	(UserRank.MODERATOR, UserRank.BOT, True),
	(UserRank.MODERATOR, UserRank.MODERATOR, False),
	(UserRank.MODERATOR, UserRank.ADMIN, False),
	(UserRank.ADMIN, UserRank.MODERATOR, True),
	(UserRank.ADMIN, UserRank.ADMIN, False),
	(UserRank.EDITOR, UserRank.MEMBER, False),
])
def test_token_permission_for_other_users(client, perm, actor_rank, target_rank, expected):
	actor = make_user("actor", actor_rank)
	target = make_user("target", target_rank)
	db.session.commit()

	assert target.check_perm(actor, perm) == expected


@pytest.mark.parametrize("perm", [Permission.CREATE_TOKEN, Permission.CREATE_OAUTH_CLIENT])
@pytest.mark.parametrize("rank", [UserRank.NEW_MEMBER, UserRank.MODERATOR, UserRank.ADMIN])
def test_token_permission_for_self(client, perm, rank):
	user = make_user("actor", rank)
	db.session.commit()

	assert user.check_perm(user, perm)


@pytest.mark.parametrize("target_rank,allowed", [
	(UserRank.MEMBER, True),
	(UserRank.MODERATOR, False),
	(UserRank.ADMIN, False),
])
def test_moderator_create_token_for_other_user(client, target_rank, allowed):
	make_user("moderator", UserRank.MODERATOR)
	target = make_user("target", target_rank)
	db.session.commit()

	login(client, "moderator", PASSWORD)

	expected_status = 200 if allowed else 403
	assert client.get("/users/target/tokens/").status_code == expected_status
	assert client.get("/users/target/tokens/new/").status_code == expected_status
	assert client.get("/users/target/apps/").status_code == expected_status

	rv = client.post("/users/target/tokens/new/", data=dict(name="impersonation"))
	assert rv.status_code == (302 if allowed else 403)
	assert APIToken.query.filter_by(owner_id=target.id).count() == (1 if allowed else 0)
