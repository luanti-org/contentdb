# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import hashlib
from types import SimpleNamespace

from app import app
from app.utils.gravatar import get_gravatar_url, get_gravatar_version, get_gravatar_proxy_url


def test_gravatar_url_uses_sha256_of_normalised_email():
	expected = hashlib.sha256(b"member@example.com").hexdigest()
	assert get_gravatar_url(" Member@Example.com ") == f"https://gravatar.com/avatar/{expected}?s=256&d=404&r=g"


def test_version_is_stable_and_case_insensitive():
	with app.app_context():
		assert get_gravatar_version("member@example.com") == get_gravatar_version("Member@Example.COM")
		assert get_gravatar_version("member@example.com") != get_gravatar_version("other@example.com")
		assert len(get_gravatar_version("member@example.com")) == 16


def test_version_doesnt_contain_hashes_of_email():
	email = b"member@example.com"
	with app.app_context():
		version = get_gravatar_version(email.decode())

	for digest in [hashlib.sha256(email).hexdigest(), hashlib.md5(email, usedforsecurity=False).hexdigest()]:
		assert version not in digest


def test_version_depends_on_secret_key(monkeypatch):
	with app.app_context():
		before = get_gravatar_version("member@example.com")
		monkeypatch.setitem(app.config, "SECRET_KEY", "different")
		assert get_gravatar_version("member@example.com") != before


def test_proxy_url_is_relative_outside_requests():
	"""
	url_for makes absolute URLs outside a request when SERVER_NAME is set, such as in tasks.
	User.get_profile_pic_url() should only be absolute when asked.
	"""
	user = SimpleNamespace(id=3, email="member@example.com")
	with app.app_context():
		assert get_gravatar_proxy_url(user).startswith("/thumbnails/gravatar/3.png?v=")  # type: ignore[arg-type]
	with app.test_request_context():
		assert get_gravatar_proxy_url(user).startswith("/thumbnails/gravatar/3.png?v=")  # type: ignore[arg-type]
