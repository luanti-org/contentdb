# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

import pytest

from app.default_data import populate_test_data
from app.models import db, User, UserRank, UserBan, APIToken, Package, Permission
from app.utils.misc import random_string
from .utils import client # noqa


@pytest.fixture
def owner_token(client):
	populate_test_data(db.session)

	owner = User.query.filter_by(username="Jeija").one()
	owner.rank = UserRank.MEMBER
	owner.is_active = True

	token = APIToken()
	token.name = "test"
	token.owner = owner
	token.access_token = random_string(32)
	db.session.add(token)
	db.session.commit()

	return owner, token.access_token


def ban(user: User, expires_at: datetime.datetime | None):
	user_ban = UserBan()
	user_ban.banned_by = User.query.filter_by(username="rubenwardy").one()
	user_ban.message = "test"
	user_ban.expires_at = expires_at
	user.ban = user_ban
	if expires_at is None:
		user.rank = UserRank.BANNED
	db.session.commit()


def whoami(client, access_token):
	return client.get("/api/whoami/", headers={"Authorization": f"Bearer {access_token}"})


def edit_package(client, access_token):
	return client.put("/api/packages/Jeija/mesecons/", json={"title": "Edited"},
			headers={"Authorization": f"Bearer {access_token}"})


def gitlab_push(client, access_token):
	return client.post("/gitlab/webhook/", headers={"X-Gitlab-Token": access_token}, json={
		"event_name": "push",
		"project": {"web_url": "https://github.com/minetest-mods/mesecons"},
		"ref": "refs/heads/not-a-release-branch",
		"after": "0" * 40,
	})


def test_api_works_when_not_banned(client, owner_token):
	_, access_token = owner_token

	rv = whoami(client, access_token)
	assert rv.status_code == 200
	assert rv.json["username"] == "Jeija"

	rv = edit_package(client, access_token)
	assert rv.status_code == 200, rv.json
	assert Package.query.filter_by(name="mesecons").one().title == "Edited"

	rv = gitlab_push(client, access_token)
	assert rv.status_code == 200
	assert rv.json["success"] is False


@pytest.mark.parametrize("expires_at", [
	datetime.datetime.now() + datetime.timedelta(days=7),
	None,
], ids=["temporary", "permanent"])
def test_api_rejects_banned_owner(client, owner_token, expires_at):
	owner, access_token = owner_token
	ban(owner, expires_at)

	assert whoami(client, access_token).status_code == 403

	assert edit_package(client, access_token).status_code == 403
	assert Package.query.filter_by(name="mesecons").one().title == "Mesecons"

	assert gitlab_push(client, access_token).status_code == 403


def test_api_works_after_ban_expires(client, owner_token):
	owner, access_token = owner_token
	ban(owner, datetime.datetime.now() - datetime.timedelta(days=1))

	assert whoami(client, access_token).status_code == 200


@pytest.mark.parametrize("expires_at", [
	datetime.datetime.now() + datetime.timedelta(days=7),
	None,
], ids=["temporary", "permanent"])
def test_banned_maintainer_has_no_package_permissions(client, owner_token, expires_at):
	owner, _ = owner_token
	package = Package.query.filter_by(name="mesecons").one()

	perms = [Permission.EDIT_PACKAGE, Permission.MAKE_RELEASE, Permission.ADD_SCREENSHOTS,
			Permission.APPROVE_RELEASE, Permission.APPROVE_SCREENSHOT, Permission.EDIT_MAINTAINERS,
			Permission.DELETE_PACKAGE, Permission.UNAPPROVE_PACKAGE]
	assert all(package.check_perm(owner, perm) for perm in perms[:4])

	ban(owner, expires_at)

	for perm in perms:
		assert not package.check_perm(owner, perm), perm
