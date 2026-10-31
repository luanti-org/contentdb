# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from unittest.mock import MagicMock

from flask import url_for

from app.blueprints.users import account
from app.models import User, UserEmailVerification, UserRank, db
from app.utils.misc import hash_token
from app.utils.user import make_flask_login_password
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


def set_password(client, password):
	return client.post("/user/set-password/", data=dict(
			password=password,
			password2=password,
	), follow_redirects=True)


def test_require_password_reset(client, monkeypatch):
	send_verify_email = MagicMock()
	monkeypatch.setattr(account, "send_verify_email", send_verify_email)

	old_password = "OldPasswordLeaked"
	new_password = "VYjNnjdDPhCVUZx"

	user = User.query.filter_by(username="rubenwardy").one()
	user.email = "rubenwardy@example.com"
	user.password = make_flask_login_password(old_password)
	db.session.commit()

	rv = login(client, "rubenwardy", old_password)
	assert is_logged_in(rv)

	rv = client.post("/admin/", data=dict(action="require_password_reset"), follow_redirects=True)
	assert b"Required 1 users to reset their password" in rv.data

	user = User.query.filter_by(username="rubenwardy").one()
	assert user.password is None
	assert user.old_password is not None
	assert user.is_password_reset_required

	# Existing sessions are forced to the set password page
	rv = client.get("/")
	assert rv.status_code == 302
	assert rv.headers["Location"].endswith("/user/set-password/")

	# Static files and stylesheets are still served
	assert client.get("/static/custom.css").status_code == 200
	assert client.get("/static/libs/bootstrap.min.css").status_code == 200

	# Help pages are still accessible
	assert client.get("/help/contact_us/").status_code == 200

	# An incorrect password gives the usual error, so a reset isn't leaked
	logout(client)
	rv = login(client, "rubenwardy", "IncorrectPassword")
	assert b"Incorrect password. Did you set one?" in rv.data
	assert b"You need to reset your password" not in rv.data
	assert not is_logged_in(rv)

	rv = login(client, user.email, "IncorrectPassword")
	assert b"Incorrect email or password" in rv.data
	assert b"You need to reset your password" not in rv.data
	assert UserEmailVerification.query.filter_by(user_id=user.id).count() == 0

	# Password login is blocked, even with the correct old password
	rv = login(client, "rubenwardy", old_password)
	assert b"You need to reset your password" in rv.data
	assert b'<a href="/help/contact_us/">contact us</a>' in rv.data
	assert not is_logged_in(rv)
	assert UserEmailVerification.query.filter_by(user_id=user.id).count() == 0

	# Logging in with the email and correct old password sends a reset email
	rv = client.post("/user/login/", data=dict(username=user.email, password=old_password))
	assert rv.status_code == 302
	assert rv.headers["Location"].endswith("/email_sent/")
	rv = client.get(rv.headers["Location"])
	assert b"sent you an email with a link" in rv.data
	assert not is_logged_in(rv)
	ver = UserEmailVerification.query.filter_by(user_id=user.id, is_password_reset=True).one()
	assert ver.email == user.email

	send_verify_email.delay.assert_called_once()
	assert send_verify_email.delay.call_args.args[0] == user.email
	token = send_verify_email.delay.call_args.args[1]
	assert ver.token_hash == hash_token(token)

	rv = client.get(url_for("users.verify_email", token=token))
	assert rv.status_code == 302
	assert rv.headers["Location"].endswith("/user/set-password/")

	rv = set_password(client, old_password)
	assert b"You cannot reuse your previous password" in rv.data
	assert User.query.filter_by(username="rubenwardy").one().is_password_reset_required

	rv = set_password(client, new_password)
	assert b"Your password has been changed successfully." in rv.data

	user = User.query.filter_by(username="rubenwardy").one()
	assert not user.is_password_reset_required
	assert user.old_password is not None

	rv = client.get("/")
	assert rv.status_code == 200

	logout(client)
	rv = login(client, "rubenwardy", new_password)
	assert is_logged_in(rv)


def test_set_password_with_email_in_use(client):
	password = "VYjNnjdDPhCVUZx"

	other = User("other_user", active=True, email="taken@example.com")
	other.rank = UserRank.MEMBER
	db.session.add(other)

	user = User.query.filter_by(username="rubenwardy").one()
	user.password = make_flask_login_password("tuckfrump")
	db.session.commit()

	login(client, "rubenwardy", "tuckfrump")
	user.password = None
	db.session.commit()

	rv = client.post("/user/set-password/", data=dict(
			email="taken@example.com",
			password=password,
			password2=password,
	), follow_redirects=True)
	assert b"Your password has been changed successfully." in rv.data

	# Discard anything that wasn't committed
	db.session.rollback()

	user = User.query.filter_by(username="rubenwardy").one()
	assert user.password is not None
	assert user.email is None
