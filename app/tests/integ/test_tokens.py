# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import time

from app.models import db, EmailSubscription
from app.utils.tokens import UNSUBSCRIBE_TOKEN_MAX_AGE_S
from .utils import client # noqa


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
