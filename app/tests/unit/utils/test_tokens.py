# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import re
import time

from flask import Flask

from app.utils.misc import hash_token
from app.utils.tokens import get_github_webhook_secret, make_unsubscribe_token, load_unsubscribe_token, \
	UNSUBSCRIBE_TOKEN_MAX_AGE_S


def make_app(secret_key="secret"):
	app = Flask(__name__)
	app.config["SECRET_KEY"] = secret_key
	return app


def test_hash_token():
	assert re.fullmatch(r"[0-9a-f]{64}", hash_token("abc"))
	assert hash_token("abc") == hash_token("abc")
	assert hash_token("abc") != hash_token("abd")


def test_github_webhook_secret():
	with make_app().app_context():
		secret = get_github_webhook_secret(1)
		assert re.fullmatch(r"[0-9a-f]{64}", secret)
		assert get_github_webhook_secret(1) == secret
		assert get_github_webhook_secret(2) != secret

	with make_app("other").app_context():
		assert get_github_webhook_secret(1) != secret


def test_unsubscribe_token():
	with make_app().app_context():
		token = make_unsubscribe_token(12)
		assert load_unsubscribe_token(token) == 12
		assert load_unsubscribe_token(make_unsubscribe_token(13)) == 13

		assert load_unsubscribe_token(token + "x") is None
		assert load_unsubscribe_token("12") is None
		assert load_unsubscribe_token("") is None

	with make_app("other").app_context():
		assert load_unsubscribe_token(token) is None


def test_unsubscribe_token_expires(monkeypatch):
	now = time.time()
	with make_app().app_context():
		monkeypatch.setattr(time, "time", lambda: now - UNSUBSCRIBE_TOKEN_MAX_AGE_S + 60)
		token = make_unsubscribe_token(12)

		monkeypatch.setattr(time, "time", lambda: now)
		assert load_unsubscribe_token(token) == 12

		monkeypatch.setattr(time, "time", lambda: now + 120)
		assert load_unsubscribe_token(token) is None
