# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
from unittest.mock import MagicMock

import pytest

from flask import url_for, g

from app import app

from app.blueprints.users import account
from app.models import User, UserEmailVerification, UserRank, UserSession, db
from app.tasks.usertasks import delete_expired_sessions
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


def get_fresh(client, url):
	# The client fixture keeps one app context for the whole test, so Flask-Login's cached user in g would
	# otherwise survive between requests
	g.pop("_login_user", None)
	return client.get(url)


def login_fresh(client, username, password):
	g.pop("_login_user", None)
	return login(client, username, password)


def copy_session(source, dest):
	with source.session_transaction() as source_sess:
		data = dict(source_sess)
	with dest.session_transaction() as dest_sess:
		dest_sess.update(data)


def get_session_token(client):
	with client.session_transaction() as sess:
		return sess["_user_id"]


def test_session_token_is_hashed(client):
	user = User.query.filter_by(username="rubenwardy").one()

	login_fresh(client, "rubenwardy", "tuckfrump")
	token = get_session_token(client)

	user_session = UserSession.query.filter_by(user_id=user.id).one()
	assert user_session.token_hash == hash_token(token)
	assert token not in user_session.token_hash

	# Knowing SECRET_KEY lets you forge a session, but the username or the stored hash isn't enough
	for forged in [user.username, user_session.token_hash]:
		with client.session_transaction() as sess:
			sess["_user_id"] = forged
		assert not is_logged_in(get_fresh(client, "/"))


def test_logout_ends_copied_session(client):
	login_fresh(client, "rubenwardy", "tuckfrump")

	copy = app.test_client()
	copy_session(client, copy)
	assert is_logged_in(get_fresh(copy, "/"))

	logout(client)
	assert UserSession.query.count() == 0
	assert not is_logged_in(get_fresh(copy, "/"))


def test_each_login_has_its_own_session(client):
	other = app.test_client()
	login_fresh(other, "rubenwardy", "tuckfrump")
	login_fresh(client, "rubenwardy", "tuckfrump")
	assert UserSession.query.count() == 2
	assert get_session_token(client) != get_session_token(other)

	assert is_logged_in(get_fresh(client, "/"))
	assert is_logged_in(get_fresh(other, "/"))


def test_change_password_ends_other_sessions(client):
	other = app.test_client()
	login_fresh(other, "rubenwardy", "tuckfrump")
	assert is_logged_in(get_fresh(other, "/"))

	login_fresh(client, "rubenwardy", "tuckfrump")
	rv = client.post("/user/change-password/", data=dict(
			old_password="tuckfrump", password="VYjNnjdDPhCVUZx", password2="VYjNnjdDPhCVUZx"),
			follow_redirects=True)
	assert b"Your password has been changed successfully." in rv.data

	assert UserSession.query.count() == 1
	assert is_logged_in(get_fresh(client, "/"))
	assert not is_logged_in(get_fresh(other, "/"))


def test_require_password_reset_ends_other_sessions(client):
	other = app.test_client()
	login_fresh(other, "rubenwardy", "tuckfrump")
	assert is_logged_in(get_fresh(other, "/"))

	login_fresh(client, "rubenwardy", "tuckfrump")
	rv = client.post("/admin/", data=dict(action="require_password_reset"), follow_redirects=True)
	assert b"Required 1 users to reset their password" in rv.data

	# The admin who ran the action keeps their session, and is sent to set a new password
	rv = get_fresh(client, "/")
	assert rv.status_code == 302
	assert rv.headers["Location"].endswith("/user/set-password/")

	# Other sessions can't be used to set a new password
	rv = get_fresh(other, "/user/set-password/")
	assert rv.status_code == 302
	assert "/user/login/" in rv.headers["Location"]


def test_switch_user_ends_admin_session(client):
	target = User("target_user", active=True)
	target.rank = UserRank.MEMBER
	db.session.add(target)
	db.session.commit()

	login_fresh(client, "rubenwardy", "tuckfrump")
	admin_copy = app.test_client()
	copy_session(client, admin_copy)

	rv = client.post("/admin/switchuser/", data=dict(username="target_user"), follow_redirects=True)
	assert b"target_user" in rv.data

	admin = User.query.filter_by(username="rubenwardy").one()
	assert UserSession.query.filter_by(user_id=admin.id).count() == 0
	assert UserSession.query.filter_by(user_id=target.id).count() == 1
	assert not is_logged_in(get_fresh(admin_copy, "/"))


@pytest.mark.parametrize("field,age", [
	("last_used_at", UserSession.IDLE_TIMEOUT),
	("created_at", UserSession.MAX_AGE),
])
def test_expired_session(client, field, age):
	login_fresh(client, "rubenwardy", "tuckfrump")
	user_session = UserSession.query.one()
	setattr(user_session, field, datetime.datetime.utcnow() - age - datetime.timedelta(minutes=1))
	db.session.commit()

	assert not is_logged_in(get_fresh(client, "/"))
	db.session.expire_all()
	assert UserSession.query.count() == 0


def test_last_used_at_is_updated(client):
	login_fresh(client, "rubenwardy", "tuckfrump")
	user_session = UserSession.query.one()

	# Recent sessions aren't written to on every request
	recent = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
	user_session.last_used_at = recent
	db.session.commit()
	get_fresh(client, "/")
	db.session.expire_all()
	assert UserSession.query.one().last_used_at == recent

	old = datetime.datetime.utcnow() - datetime.timedelta(days=1)
	UserSession.query.one().last_used_at = old
	db.session.commit()
	assert is_logged_in(get_fresh(client, "/"))
	db.session.expire_all()
	assert UserSession.query.one().last_used_at > recent


def test_delete_expired_sessions(client):
	user = User.query.filter_by(username="rubenwardy").one()
	now = datetime.datetime.utcnow()
	for i, (created_at, last_used_at) in enumerate([
		(now, now),
		(now - UserSession.MAX_AGE - datetime.timedelta(days=1), now),
		(now, now - UserSession.IDLE_TIMEOUT - datetime.timedelta(days=1)),
	]):
		user_session = UserSession()
		user_session.user = user
		user_session.token_hash = hash_token(str(i))
		user_session.created_at = created_at
		user_session.last_used_at = last_used_at
		db.session.add(user_session)
	db.session.commit()

	delete_expired_sessions()
	db.session.expire_all()
	assert [x.token_hash for x in UserSession.query.all()] == [hash_token("0")]


def test_login_again_ends_previous_session(client):
	target = User("target_user", active=True, email="target@example.com")
	target.rank = UserRank.MEMBER
	db.session.add(target)
	ver = UserEmailVerification()
	ver.user = target
	ver.token_hash = hash_token("reset-token")
	ver.email = target.email
	ver.is_password_reset = True
	db.session.add(ver)
	db.session.commit()

	login_fresh(client, "rubenwardy", "tuckfrump")
	old_copy = app.test_client()
	copy_session(client, old_copy)

	# Opening a password reset link logs in as that user, replacing the current session
	g.pop("_login_user", None)
	rv = client.get(url_for("users.verify_email", token="reset-token"))
	assert rv.headers["Location"].endswith("/user/set-password/")

	admin = User.query.filter_by(username="rubenwardy").one()
	assert UserSession.query.filter_by(user_id=admin.id).count() == 0
	assert not is_logged_in(get_fresh(old_copy, "/"))


def test_modtools_rank_banned_ends_sessions(client):
	target = User("target_user", active=True)
	target.rank = UserRank.MEMBER
	target.password = make_flask_login_password("password123")
	db.session.add(target)
	db.session.commit()

	other = app.test_client()
	login_fresh(other, "target_user", "password123")
	assert UserSession.query.filter_by(user_id=target.id).count() == 1

	login_fresh(client, "rubenwardy", "tuckfrump")
	client.post("/users/target_user/modtools/", data=dict(
			username="target_user", display_name="target_user", rank="BANNED"), follow_redirects=True)

	db.session.expire_all()
	assert User.query.filter_by(username="target_user").one().rank == UserRank.BANNED
	assert UserSession.query.filter_by(user_id=target.id).count() == 0
