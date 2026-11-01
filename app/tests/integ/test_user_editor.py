# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from app.models import db, User, UserRank
from app.utils.user import make_flask_login_password
from .utils import login
from .utils import client # noqa


PASSWORD = "VYjNnjdDPhCVUZx"

DELETABLE = ["new_member", "member", "trusted_member", "editor", "banned"]
PROTECTED = ["other_moderator", "admin"]


def setup_users(client):
	for username, rank in [
		("moderator", UserRank.MODERATOR),
		("new_member", UserRank.NEW_MEMBER),
		("member", UserRank.MEMBER),
		("trusted_member", UserRank.TRUSTED_MEMBER),
		("editor", UserRank.EDITOR),
		("banned", UserRank.BANNED),
		("other_moderator", UserRank.MODERATOR),
		("admin", UserRank.ADMIN),
	]:
		user = User(username, active=True, password=make_flask_login_password(PASSWORD))
		user.rank = rank
		db.session.add(user)
	db.session.commit()

	login(client, "moderator", PASSWORD)


def remaining(usernames: list[str]) -> list[str]:
	return sorted(x.username for x in User.query.filter(User.username.in_(usernames)).all())


def test_user_editor_delete_confirmation_excludes_moderators(client):
	setup_users(client)

	rv = client.post("/admin/users/delete/", data=dict(selected=DELETABLE + PROTECTED))
	assert rv.status_code == 200
	assert f"Delete {len(DELETABLE)} Users".encode() in rv.data
	for username in DELETABLE:
		assert f'value="{username}"'.encode() in rv.data
	for username in PROTECTED:
		assert f'value="{username}"'.encode() not in rv.data

	assert remaining(DELETABLE + PROTECTED) == sorted(DELETABLE + PROTECTED)


def test_user_editor_delete_skips_moderators(client):
	setup_users(client)

	rv = client.post("/admin/users/delete/", data=dict(selected=DELETABLE + PROTECTED, confirm="1"),
			follow_redirects=True)
	assert f"Deleted {len(DELETABLE)} users".encode() in rv.data

	assert remaining(DELETABLE) == []
	assert remaining(PROTECTED) == sorted(PROTECTED)


def test_user_editor_list_hides_moderators(client):
	setup_users(client)

	rv = client.get("/admin/users/?min_rank=BANNED&max_rank=ADMIN")
	assert rv.status_code == 200
	for username in DELETABLE:
		assert f"/users/{username}/".encode() in rv.data
	for username in PROTECTED:
		assert f"/users/{username}/".encode() not in rv.data
