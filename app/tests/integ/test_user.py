# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from unittest.mock import MagicMock

from flask import url_for

from app.blueprints.users import account
from app.models import User, UserEmailVerification
from app.utils.misc import hash_token
from .utils import login, logout, is_logged_in
from .utils import client # noqa


def test_login_logout(client):
	rv = client.get("/")
	assert not is_logged_in(rv)

	assert b"Sign out" not in rv.data
	rv = login(client, "rubenwardy", "tuckfrump")
	assert b"Sign out" in rv.data
	assert is_logged_in(rv)

	rv = client.get("/")
	assert is_logged_in(rv)

	rv = logout(client)
	assert not is_logged_in(rv)

	rv = login(client, "rubenwardy", "wrongpass")
	assert b"Incorrect password. Did you set one?" in rv.data
	assert not is_logged_in(rv)

	rv = login(client, "badname", "wrongpass")
	assert b"User badname does not exist" in rv.data
	assert not is_logged_in(rv)

	rv = login(client, "bad@email.com", "wrongpass")
	assert b"Incorrect email or password" in rv.data
	assert not is_logged_in(rv)


def register(client, username, display_name, password, email, question):
	return client.post("/user/register/", data=dict(
			username=username,
			display_name=display_name,
			email=email,
			password=password,
			question=question,
			agree=True
	), follow_redirects=True)


def test_register(client):
	username = "testuser123"
	password = "VYjNnjdDPhCVUZx"
	assert User.query.filter_by(username=username).first() is None

	rv = register(client, username, "Test User", "password", "test@example.com", "13")
	assert b"Field must be between 12 and 100 characters long." in rv.data

	rv = register(client, username, "Test User", password, "test@example.com", "13")
	assert b"Incorrect captcha answer" in rv.data

	rv = register(client, "££££!!!", "Test User", password, "test@example.com", "13")
	assert b"invalid-feedback" in rv.data
	assert b"Only alphabetic letters (A-Za-z), numbers (0-9), underscores (_), minuses (-), and periods (.) allowed</p>" in rv.data


def test_register_flow(client, monkeypatch):
	send_verify_email = MagicMock()
	monkeypatch.setattr(account, "send_verify_email", send_verify_email)

	username = "testuser123"
	password = "VYjNnjdDPhCVUZx"

	assert User.query.filter_by(username=username).first() is None

	rv = register(client, username, "Test User", password, "test@example.com", "19")
	assert b"We've sent an email to the address you specified" in rv.data

	user = User.query.filter_by(username=username).first()
	assert user is not None
	assert user.username == username
	assert user.display_name == "Test User"
	assert not user.is_active
	assert user.email_confirmed_at is None
	assert user.email == "test@example.com"

	rv = login(client, username, password)
	assert b"You need to confirm the registration email" in rv.data
	assert not is_logged_in(rv)

	email = UserEmailVerification.query.filter_by(user_id=user.id).first()
	assert email is not None

	# Only the hash is stored, the token is sent by email
	send_verify_email.delay.assert_called_once()
	token = send_verify_email.delay.call_args.args[1]
	assert email.token_hash == hash_token(token)
	assert token not in email.token_hash

	rv = client.get(url_for('users.verify_email', token="wrong" + token), follow_redirects=True)
	assert b"Unknown verification token!" in rv.data

	rv = client.get(url_for('users.verify_email', token=token), follow_redirects=True)
	assert b"You may now log in" in rv.data

	assert b"Sign out" not in rv.data
	rv = login(client, username, password)
	assert b"Sign out" in rv.data
	assert is_logged_in(rv)
