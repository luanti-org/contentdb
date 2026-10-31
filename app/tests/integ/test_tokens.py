# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import time

from app.models import db, User, UserRank, EmailSubscription, UserEmailVerification
from app.utils.misc import hash_token, random_string
from app.utils.tokens import UNSUBSCRIBE_TOKEN_MAX_AGE_S
from app.utils.user import make_flask_login_password
from .utils import login
from .utils import client # noqa


def make_user(username, rank, email=None):
	user = User(username)
	user.is_active = True
	user.email = email
	user.email_confirmed_at = datetime.datetime.now()
	user.password = make_flask_login_password("password123")
	user.rank = rank
	db.session.add(user)
	db.session.commit()
	return user


def test_unsubscribe_signed_token(client):
	sub = EmailSubscription("test@example.com")
	db.session.add(sub)
	db.session.commit()

	rv = client.get(sub.url)
	assert rv.status_code == 200
	assert b'name="email"' not in rv.data

	rv = client.get(sub.url + "x")
	assert rv.status_code == 200
	assert b'name="email"' in rv.data
	assert b"invalid or has expired" in rv.data

	rv = client.get("/unsubscribe/?token=" + str(sub.id))
	assert b'name="email"' in rv.data

	rv = client.get("/unsubscribe/")
	assert b'name="email"' in rv.data
	assert b"invalid or has expired" not in rv.data


def test_unsubscribe_link_expires(client, monkeypatch):
	sub = EmailSubscription("test@example.com")
	db.session.add(sub)
	db.session.commit()

	url = sub.url
	monkeypatch.setattr(time, "time", lambda now=time.time(): now + UNSUBSCRIBE_TOKEN_MAX_AGE_S + 60)

	rv = client.get(url)
	assert b'name="email"' in rv.data
	assert b"invalid or has expired" in rv.data


def make_email_verification(user, email):
	ver = UserEmailVerification()
	ver.user = user
	ver.email = email
	ver.token_hash = hash_token(random_string(32))
	db.session.add(ver)
	db.session.commit()
	return ver.id


def test_modtools_verify_email(client):
	user = make_user("member", UserRank.MEMBER, "old@example.com")
	make_user("mod", UserRank.MODERATOR)
	ver_id = make_email_verification(user, "new@example.com")

	login(client, "mod", "password123")
	rv = client.post(f"/users/member/modtools/verify-email/{ver_id}/", follow_redirects=True)
	assert rv.status_code == 200

	db.session.expire_all()
	assert User.query.filter_by(username="member").one().email == "new@example.com"
	assert UserEmailVerification.query.get(ver_id) is None


def test_modtools_verify_email_requires_mod(client):
	user = make_user("member", UserRank.MEMBER, "old@example.com")
	make_user("other", UserRank.MEMBER)
	ver_id = make_email_verification(user, "new@example.com")

	login(client, "other", "password123")
	rv = client.post(f"/users/member/modtools/verify-email/{ver_id}/")
	assert rv.status_code == 403

	db.session.expire_all()
	assert User.query.filter_by(username="member").one().email == "old@example.com"
	assert UserEmailVerification.query.get(ver_id) is not None
