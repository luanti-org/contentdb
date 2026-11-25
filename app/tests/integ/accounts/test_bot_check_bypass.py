# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
The cookie that lets members skip Anubis's proof of work. Anubis only checks it's present, so ContentDB must
reject requests where it isn't valid.
"""

import time

import pytest
from itsdangerous import TimestampSigner, URLSafeTimedSerializer

from app.models import db, UserRank
from app.utils.bot_check_bypass import COOKIE_NAME, MAX_AGE, REFRESH_AFTER, make_bypass_token, _get_serializer
from ..factories import create_user, login_as, client_request


def get_cookie_value(client) -> str | None:
	cookie = client.get_cookie(COOKIE_NAME)
	return cookie.value if cookie else None


def load_cookie(client, max_age: int | None = None) -> int:
	value = get_cookie_value(client)
	assert value is not None
	return _get_serializer().loads(value, max_age=max_age)


def set_cookie(client, value: str):
	client.set_cookie(COOKIE_NAME, value, domain="localhost")


def make_old_token(user_id: int, age_s: float, monkeypatch) -> str:
	now = time.time()
	with monkeypatch.context() as m:
		m.setattr(TimestampSigner, "get_timestamp", lambda self: int(now - age_s))
		return make_bypass_token(user_id)


def assert_rejected(rv, url: str):
	assert rv.status_code == 307
	assert rv.headers["Location"] == url


@pytest.mark.parametrize("rank", [UserRank.MEMBER, UserRank.TRUSTED_MEMBER, UserRank.ADMIN])
def test_set_for_members_and_above(client, rank):
	user = create_user("alice", rank=rank)
	login_as(client, user)

	rv = client_request(client, "GET", "/")

	assert rv.status_code == 200
	assert load_cookie(client) == user.id


@pytest.mark.parametrize("rank", [UserRank.NEW_MEMBER, UserRank.BANNED])
def test_not_set_below_member(client, rank):
	login_as(client, create_user("alice", rank=rank))

	client_request(client, "GET", "/")

	assert get_cookie_value(client) is None


def test_not_set_when_logged_out(client):
	rv = client_request(client, "GET", "/")

	assert rv.status_code == 200
	assert get_cookie_value(client) is None


def test_valid_cookie_is_accepted(client):
	user = create_user("alice")
	login_as(client, user)
	token = make_bypass_token(user.id)
	set_cookie(client, token)

	rv = client_request(client, "GET", "/")

	assert rv.status_code == 200
	assert get_cookie_value(client) == token


def test_old_cookie_is_refreshed(client, monkeypatch):
	user = create_user("alice")
	login_as(client, user)
	old_token = make_old_token(user.id, REFRESH_AFTER.total_seconds() + 60, monkeypatch)
	set_cookie(client, old_token)

	rv = client_request(client, "GET", "/")

	assert rv.status_code == 200
	assert get_cookie_value(client) != old_token
	assert load_cookie(client, max_age=60) == user.id


def test_forged_cookie_is_rejected_when_logged_out(client):
	set_cookie(client, "forged")

	rv = client_request(client, "GET", "/packages/?q=test")

	assert_rejected(rv, "/packages/?q=test")
	assert get_cookie_value(client) is None


def test_forged_cookie_is_rejected_and_replaced_for_member(client):
	user = create_user("alice")
	login_as(client, user)
	set_cookie(client, "forged")

	rv = client_request(client, "GET", "/packages/")

	assert_rejected(rv, "/packages/")
	assert load_cookie(client) == user.id

	rv = client_request(client, "GET", "/packages/")
	assert rv.status_code == 200


def test_cookie_signed_with_another_key_is_rejected(client):
	user = create_user("alice")
	login_as(client, user)
	set_cookie(client, URLSafeTimedSerializer("not the secret key", salt="bot-check-bypass").dumps(user.id))

	rv = client_request(client, "GET", "/")

	assert_rejected(rv, "/")


def test_expired_cookie_is_rejected(client, monkeypatch):
	user = create_user("alice")
	login_as(client, user)
	set_cookie(client, make_old_token(user.id, MAX_AGE.total_seconds() + 60, monkeypatch))

	rv = client_request(client, "GET", "/")

	assert_rejected(rv, "/")


def test_cookie_for_another_user_is_rejected(client):
	login_as(client, create_user("alice"))
	set_cookie(client, make_bypass_token(create_user("bob").id))

	rv = client_request(client, "GET", "/")

	assert_rejected(rv, "/")


def test_valid_cookie_is_rejected_when_logged_out(client):
	user = create_user("alice")
	set_cookie(client, make_bypass_token(user.id))

	rv = client_request(client, "GET", "/")

	assert_rejected(rv, "/")
	assert get_cookie_value(client) is None


def test_cookie_is_rejected_after_demotion(client):
	user = create_user("alice")
	login_as(client, user)
	client_request(client, "GET", "/")
	assert get_cookie_value(client) is not None

	user.rank = UserRank.NEW_MEMBER
	db.session.commit()

	rv = client_request(client, "GET", "/")

	assert_rejected(rv, "/")
	assert get_cookie_value(client) is None


def test_rejecting_post_keeps_method(client):
	set_cookie(client, "forged")

	rv = client_request(client, "POST", "/user/login/", data={"username": "alice", "password": "x"})

	assert_rejected(rv, "/user/login/")


def test_logout_deletes_cookie(client):
	login_as(client, create_user("alice"))
	client_request(client, "GET", "/")
	assert get_cookie_value(client) is not None

	rv = client_request(client, "POST", "/user/logout/")

	assert rv.status_code == 302
	assert get_cookie_value(client) is None


def test_banned_user_cookie_is_deleted(client):
	user = create_user("alice")
	login_as(client, user)
	client_request(client, "GET", "/")
	assert get_cookie_value(client) is not None

	user.rank = UserRank.BANNED
	db.session.commit()

	rv = client_request(client, "GET", "/")

	# check_for_ban logs out and redirects to the login page
	assert rv.status_code == 302
	assert get_cookie_value(client) is None
