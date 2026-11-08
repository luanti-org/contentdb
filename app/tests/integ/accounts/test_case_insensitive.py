# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.blueprints.users import account, settings
from app.models import User, UserRank, UserEmailVerification, EmailSubscription, db
from app.utils.user import make_flask_login_password
from ..utils import login, is_logged_in


PASSWORD = "VYjNnjdDPhCVUZx"


def set_rubenwardy_email(email):
	user = User.query.filter_by(username="rubenwardy").one()
	user.email = email
	user.password = make_flask_login_password(PASSWORD)
	db.session.commit()
	return user


def test_login_ignores_email_case(client):
	set_rubenwardy_email("Ruben@Example.com")

	rv = login(client, "rUBEN@example.COM", PASSWORD)
	assert is_logged_in(rv)


def test_unique_email_ignores_case(client):
	set_rubenwardy_email("ruben@example.com")

	other = User("other_user", active=True, email="RUBEN@example.com")
	db.session.add(other)
	with pytest.raises(IntegrityError):
		db.session.commit()
	db.session.rollback()


def test_unique_email_subscription_ignores_case(client):
	db.session.add(EmailSubscription("sub@example.com"))
	db.session.commit()

	db.session.add(EmailSubscription("SUB@example.com"))
	with pytest.raises(IntegrityError):
		db.session.commit()
	db.session.rollback()


def test_register_with_email_in_use_ignores_case(client, monkeypatch):
	send_anon_email = MagicMock()
	monkeypatch.setattr("app.domain.users.send_anon_email", send_anon_email)
	set_rubenwardy_email("ruben@example.com")

	rv = client.post("/user/register/", data=dict(
			username="testuser123",
			display_name="Test User",
			email="Ruben@Example.com",
			password=PASSWORD,
			question="19",
			agree=True
	), follow_redirects=True)
	assert b"We've sent an email to the address you specified" in rv.data
	assert User.query.filter_by(username="testuser123").first() is None
	send_anon_email.delay.assert_called_once()


def test_blacklist_ignores_case(client):
	sub = EmailSubscription("blocked@example.com")
	sub.blacklisted = True
	db.session.add(sub)
	set_rubenwardy_email("ruben@example.com")

	login(client, "rubenwardy", PASSWORD)
	rv = client.post("/users/rubenwardy/settings/email/", data=dict(email="Blocked@Example.com"), follow_redirects=True)
	assert b"has been unsubscribed/blacklisted" in rv.data
	assert User.query.filter_by(username="rubenwardy").one().email == "ruben@example.com"


def test_change_email_casing_without_verification(client, monkeypatch):
	send_verify_email = MagicMock()
	monkeypatch.setattr(settings, "send_verify_email", send_verify_email)
	set_rubenwardy_email("ruben@example.com")

	login(client, "rubenwardy", PASSWORD)
	rv = client.post("/users/rubenwardy/settings/email/", data=dict(email="Ruben@Example.com"), follow_redirects=True)
	assert rv.status_code == 200

	send_verify_email.delay.assert_not_called()
	assert UserEmailVerification.query.count() == 0
	assert User.query.filter_by(username="rubenwardy").one().email == "Ruben@Example.com"


def test_verify_email_casing_change(client):
	"""An email verification that only changes case isn't blocked by the user's own email"""
	user = set_rubenwardy_email("ruben@example.com")

	ver = UserEmailVerification()
	ver.user = user
	ver.email = "Ruben@Example.com"
	db.session.add(ver)
	db.session.commit()

	login(client, "rubenwardy", PASSWORD)
	with client.application.test_request_context():
		assert account.confirm_email_verification(ver)

	assert User.query.filter_by(username="rubenwardy").one().email == "Ruben@Example.com"


def test_verify_email_taken_by_other_user_ignores_case(client):
	user = set_rubenwardy_email("ruben@example.com")
	other = User("other_user", active=True, email="taken@example.com")
	other.rank = UserRank.MEMBER
	db.session.add(other)

	ver = UserEmailVerification()
	ver.user = user
	ver.email = "Taken@Example.com"
	db.session.add(ver)
	db.session.commit()

	with client.application.test_request_context():
		assert not account.confirm_email_verification(ver)

	assert User.query.filter_by(username="rubenwardy").one().email == "ruben@example.com"


def test_forgot_password_ignores_case(client, monkeypatch):
	send_password_reset_email = MagicMock()
	monkeypatch.setattr(account, "send_password_reset_email", send_password_reset_email)
	set_rubenwardy_email("ruben@example.com")

	client.post("/user/forgot-password/", data=dict(email="RUBEN@example.com"), follow_redirects=True)

	send_password_reset_email.assert_called_once()
	# Sent to the stored address, not the typed one
	assert send_password_reset_email.call_args.args[1] == "ruben@example.com"


def test_unique_username_ignores_case(client):
	db.session.add(User("RubenWardy", active=True))
	with pytest.raises(IntegrityError):
		db.session.commit()
	db.session.rollback()


def test_username_lookup_ignores_case(client):
	assert User.query.filter_by(username="RUBENWARDY").one().username == "rubenwardy"

	rv = client.get("/users/RubenWardy/")
	assert rv.status_code == 200
