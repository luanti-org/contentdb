# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import hashlib

from sqlalchemy import text

from app.models import User, EmailSubscription, db
from .utils import client # noqa


def set_rubenwardy_email(email):
	user = User.query.filter_by(username="rubenwardy").one()
	user.email = email
	db.session.commit()
	return user


def test_email_is_stored_hashed(client):
	sub = EmailSubscription("Sub@Example.com")
	db.session.add(sub)
	db.session.commit()

	row = db.session.execute(text("SELECT * FROM email_subscription WHERE id = :id"), {"id": sub.id}).mappings().one()
	assert "email" not in row
	assert row["email_hash"] == hashlib.sha256(b"sub@example.com").hexdigest()


def test_query_by_email_ignores_case(client):
	sub = EmailSubscription("sub@example.com")
	db.session.add(sub)
	db.session.commit()

	assert EmailSubscription.query_by_email("SUB@Example.COM").one().id == sub.id
	assert EmailSubscription.query_by_email("other@example.com").first() is None


def test_find_user_matches_python_hash(client):
	"""find_user hashes in SQL, which must agree with hash_email"""
	user = set_rubenwardy_email("Ruben@Example.com")

	sub = EmailSubscription("ruben@example.COM")
	db.session.add(sub)
	db.session.commit()
	assert sub.find_user() == user

	other = EmailSubscription("nobody@example.com")
	db.session.add(other)
	db.session.commit()
	assert other.find_user() is None


def test_unsubscribe_blacklists_and_clears_user_email(client):
	set_rubenwardy_email("ruben@example.com")

	sub = EmailSubscription("Ruben@Example.com")
	db.session.add(sub)
	db.session.commit()

	rv = client.post(sub.url, follow_redirects=True)
	assert rv.status_code == 200

	assert EmailSubscription.query_by_email("ruben@example.com").one().blacklisted
	assert User.query.filter_by(username="rubenwardy").one().email is None
