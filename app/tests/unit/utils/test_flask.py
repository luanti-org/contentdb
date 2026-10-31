# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import Flask

from app.utils.flask import is_safe_url


def check_safe_url(target):
	app = Flask(__name__)
	with app.test_request_context("/", base_url="https://content.luanti.org"):
		return is_safe_url(target)


def test_is_safe_url_allows_local():
	assert check_safe_url("/packages/")
	assert check_safe_url("/packages/?q=a/b")
	assert check_safe_url("https://content.luanti.org/packages/")
	assert check_safe_url("packages/")


def test_is_safe_url_rejects_external():
	assert not check_safe_url("https://evil.com")
	assert not check_safe_url("//evil.com")
	assert not check_safe_url("javascript:alert(1)")


def test_is_safe_url_rejects_backslash():
	assert not check_safe_url("/\\evil.com")
	assert not check_safe_url("\\\\evil.com")
	assert not check_safe_url("/\\/evil.com")


def test_is_safe_url_rejects_control_chars():
	assert not check_safe_url("/\t/evil.com")
	assert not check_safe_url("/\n/evil.com")
