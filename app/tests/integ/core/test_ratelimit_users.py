# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from unittest.mock import MagicMock

import pytest

from app import app
from app.blueprints.users import account, claim, profile
from app.domain import users as domain_users
from app.models import db, User, UserRank
from app.utils.ratelimit import get_client_ip_key
from app.utils.user import make_flask_login_password
from ..utils import login, is_logged_in


@pytest.mark.parametrize("addr, expected", [
	("203.0.113.5", "203.0.113.5"),
	("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
	("2001:db8:1:2:ffff::1", "2001:db8:1:2::/64"),
	("::ffff:203.0.113.5", "203.0.113.5"),
])
def test_client_ip_key(addr, expected):
	with app.test_request_context(environ_base={"REMOTE_ADDR": addr}):
		assert get_client_ip_key() == expected


@pytest.fixture
def emails(monkeypatch):
	send_verify_email = MagicMock()
	send_anon_email = MagicMock()
	monkeypatch.setattr(account, "send_verify_email", send_verify_email)
	monkeypatch.setattr(account, "send_anon_email", send_anon_email)
	monkeypatch.setattr(domain_users, "send_anon_email", send_anon_email)
	monkeypatch.setattr(account, "send_unsubscribe_verify", MagicMock())

	def count():
		return send_verify_email.delay.call_count + send_anon_email.delay.call_count

	return count


def forgot_password(client, email: str, ip: str = "203.0.113.5"):
	return client.post("/user/forgot-password/", data=dict(email=email), headers={"X-Forwarded-For": ip},
			follow_redirects=True)


def test_email_limit_per_address_and_ip(client, emails):
	for _ in range(5):
		forgot_password(client, "nobody@example.com")
	assert emails() == 5

	rv = forgot_password(client, "nobody@example.com")
	assert b"Too many emails have been sent recently" in rv.data
	assert emails() == 5

	# Other addresses and other clients aren't affected, so the owner of the address can still get emails
	forgot_password(client, "someone@example.com")
	forgot_password(client, "nobody@example.com", ip="198.51.100.1")
	assert emails() == 7


def test_email_limit_per_address(client, emails):
	for i in range(20):
		forgot_password(client, "nobody@example.com", ip=f"198.51.100.{i // 5}")
	assert emails() == 20

	rv = forgot_password(client, "nobody@example.com", ip="198.51.100.99")
	assert b"Too many emails have been sent recently" in rv.data
	assert emails() == 20


def test_email_limit_is_the_same_whether_or_not_account_exists(client, emails):
	user = User.query.filter_by(username="rubenwardy").one()
	user.email = "ruben@example.com"
	db.session.commit()

	for _ in range(5):
		forgot_password(client, "ruben@example.com")

	rv = forgot_password(client, "ruben@example.com")
	assert b"Too many emails have been sent recently" in rv.data
	assert emails() == 5


def test_email_limit_per_ip(client, emails):
	for i in range(10):
		forgot_password(client, f"person{i}@example.com")
	assert emails() == 10

	rv = forgot_password(client, "another@example.com")
	assert b"Too many emails have been sent recently" in rv.data
	assert emails() == 10

	forgot_password(client, "another@example.com", ip="198.51.100.1")
	assert emails() == 11


def test_email_limit_shared_between_routes(client, emails):
	for _ in range(5):
		forgot_password(client, "victim@example.com")

	rv = client.post("/unsubscribe/", data=dict(email="victim@example.com"), headers={"X-Forwarded-For": "203.0.113.5"},
			follow_redirects=True)
	assert b"Too many emails have been sent recently" in rv.data
	assert emails() == 5


def login_from(client, username: str, password: str, ip: str = "203.0.113.5"):
	return client.post("/user/login/", data=dict(username=username, password=password),
			headers={"X-Forwarded-For": ip}, follow_redirects=True)


def test_failed_login_limit(client):
	for _ in range(10):
		rv = login_from(client, "rubenwardy", "wrongpass")
		assert b"Incorrect password" in rv.data

	# Even the right password is refused, so a limited client can't keep guessing
	rv = login_from(client, "rubenwardy", "tuckfrump")
	assert b"Too many failed sign in attempts" in rv.data
	assert not is_logged_in(rv)

	# The account isn't locked for everyone else
	rv = login_from(client, "rubenwardy", "tuckfrump", ip="198.51.100.1")
	assert is_logged_in(rv)


def test_failed_login_limit_per_ip(client):
	for i in range(30):
		login_from(client, f"user{i}", "wrongpass")

	rv = login_from(client, "rubenwardy", "tuckfrump")
	assert b"Too many failed sign in attempts" in rv.data


def test_every_login_attempt_counts_per_account_and_ip(client):
	# Recorded before the password is checked, so that requests at the same time can't all get past the limit
	for _ in range(10):
		rv = login_from(client, "rubenwardy", "tuckfrump")
		assert is_logged_in(rv)
		client.post("/user/logout/")

	rv = login_from(client, "rubenwardy", "tuckfrump")
	assert b"Too many failed sign in attempts" in rv.data


def test_successful_logins_do_not_count_per_ip(client):
	# So that many people can sign in from one shared IP
	for i in range(4):
		user = User(f"sharer{i}", True)
		user.rank = UserRank.MEMBER
		user.password = make_flask_login_password("password")
		db.session.add(user)
	db.session.commit()

	for i in range(4):
		for _ in range(9):
			rv = login_from(client, f"sharer{i}", "password")
			assert is_logged_in(rv)
			client.post("/user/logout/")

	rv = login_from(client, "rubenwardy", "wrongpass")
	assert b"Incorrect password" in rv.data


def test_claim_forums_limit(client, monkeypatch):
	get_profile = MagicMock(return_value=None)
	monkeypatch.setattr(claim, "get_profile", get_profile)

	for i in range(5):
		client.post("/user/claim-forums/", data=dict(claim_type="forum", username=f"forumuser{i}"))
	assert get_profile.call_count == 5

	rv = client.post("/user/claim-forums/", data=dict(claim_type="forum", username="forumuser5"), follow_redirects=True)
	assert b"Too many attempts" in rv.data
	assert get_profile.call_count == 5


def test_check_forums_limit(client, monkeypatch):
	check_forum_account = MagicMock()
	check_forum_account.delay.return_value.id = "fake"
	monkeypatch.setattr(profile, "check_forum_account", check_forum_account)

	user = User("forumer", True)
	user.rank = UserRank.MEMBER
	user.forums_username = "forumer"
	user.password = make_flask_login_password("password")
	db.session.add(user)
	db.session.commit()
	login(client, "forumer", "password")

	for _ in range(5):
		client.post("/users/forumer/check-forums/")
	assert check_forum_account.delay.call_count == 5

	rv = client.post("/users/forumer/check-forums/", follow_redirects=True)
	assert b"Too many attempts" in rv.data
	assert check_forum_account.delay.call_count == 5


def test_spoofed_forwarded_for_is_ignored(client, emails):
	# Our proxy appends the real client IP, so earlier values were sent by the client and can't be trusted
	for i in range(10):
		forgot_password(client, f"person{i}@example.com", ip=f"198.51.100.{i}, 203.0.113.5")

	rv = forgot_password(client, "another@example.com", ip="198.51.100.99, 203.0.113.5")
	assert b"Too many emails have been sent recently" in rv.data
	assert emails() == 10


def register_from(client, username: str, email: str, ip: str = "203.0.113.5"):
	return client.post("/user/register/", data=dict(username=username, email=email, password="a password long enough",
			question="19"), headers={"X-Forwarded-For": ip}, follow_redirects=True)


def test_rejected_registration_does_not_count(client, emails):
	# The username is taken, so the registration fails without sending an email
	for _ in range(10):
		register_from(client, "rubenwardy", "new@example.com")
	assert emails() == 0

	register_from(client, "newuser", "new@example.com")
	assert emails() == 1


def test_registration_with_email_in_use_counts(client, emails):
	user = User.query.filter_by(username="rubenwardy").one()
	user.email = "ruben@example.com"
	db.session.commit()

	for i in range(5):
		register_from(client, f"newuser{i}", "ruben@example.com")
	assert emails() == 5

	rv = register_from(client, "newuser5", "ruben@example.com")
	assert b"Too many emails have been sent recently" in rv.data
	assert emails() == 5


def test_claim_forums_is_not_limited_per_forum_user(client, monkeypatch):
	# Otherwise, anyone could stop a user from claiming their forum account
	get_profile = MagicMock(return_value=None)
	monkeypatch.setattr(claim, "get_profile", get_profile)

	for i in range(15):
		client.post("/user/claim-forums/", data=dict(claim_type="forum", username="victim"),
				headers={"X-Forwarded-For": f"198.51.100.{i // 5}"})
	assert get_profile.call_count == 15
