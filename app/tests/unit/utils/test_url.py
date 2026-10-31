# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from app.utils import url
from app.utils.url import clean_youtube_url, is_valid_oauth_redirect_url


def test_clean_youtube_url():
	assert clean_youtube_url(
		"https://www.youtube.com/watch?v=AABBCC") == "https://www.youtube.com/watch?v=AABBCC"
	assert clean_youtube_url(
		"https://www.youtube.com/watch?v=boGcB4H5-WA&other=1") == "https://www.youtube.com/watch?v=boGcB4H5-WA"
	assert clean_youtube_url("https://www.youtube.com/watch?kk=boGcB4H5-WA&other=1") is None
	assert clean_youtube_url("https://www.bob.com/watch?v=AABBCC") is None

	assert clean_youtube_url("https://youtu.be/boGcB4H5-WA") == "https://www.youtube.com/watch?v=boGcB4H5-WA"
	assert clean_youtube_url("https://youtu.be/boGcB4H5-WA?this=1") == "https://www.youtube.com/watch?v=boGcB4H5-WA"


def test_is_valid_oauth_redirect_url_allows():
	assert is_valid_oauth_redirect_url("https://example.com/callback/")
	assert is_valid_oauth_redirect_url("https://example.com/callback/?a=b")
	assert is_valid_oauth_redirect_url("https://example.com:8080/callback/")
	assert is_valid_oauth_redirect_url("http://localhost/callback/")
	assert is_valid_oauth_redirect_url("http://localhost:8000/callback/")
	assert is_valid_oauth_redirect_url("http://127.0.0.1:8000/callback/")
	assert is_valid_oauth_redirect_url("http://[::1]:8000/callback/")


def test_is_valid_oauth_redirect_url_rejects_schemes():
	assert not is_valid_oauth_redirect_url("http://example.com/callback/")
	assert not is_valid_oauth_redirect_url("http://localhost.example.com/callback/")
	assert not is_valid_oauth_redirect_url("javascript:alert(1)")
	assert not is_valid_oauth_redirect_url("JavaScript:alert(1)")
	assert not is_valid_oauth_redirect_url("data:text/html,hi")
	assert not is_valid_oauth_redirect_url("ftp://example.com/")
	assert not is_valid_oauth_redirect_url("//example.com/callback/")
	assert not is_valid_oauth_redirect_url("/callback/")
	assert not is_valid_oauth_redirect_url("example.com/callback/")
	assert not is_valid_oauth_redirect_url("https:///callback/")
	assert not is_valid_oauth_redirect_url("")


def test_is_valid_oauth_redirect_url_rejects_tricks():
	assert not is_valid_oauth_redirect_url("https://example.com/callback/#frag")
	assert not is_valid_oauth_redirect_url("https://example.com/callback/#")
	assert not is_valid_oauth_redirect_url("https:\\\\example.com/callback/")
	assert not is_valid_oauth_redirect_url("https://example.com/call back/")
	assert not is_valid_oauth_redirect_url("java\tscript:alert(1)")
	assert not is_valid_oauth_redirect_url("https://[::1/callback/")


def test_is_valid_oauth_redirect_url_custom_scheme(monkeypatch):
	assert not is_valid_oauth_redirect_url("myapp://callback")

	monkeypatch.setattr(url, "OAUTH_ALLOWED_CUSTOM_SCHEMES", {"myapp"})
	assert is_valid_oauth_redirect_url("myapp://callback")
	assert not is_valid_oauth_redirect_url("otherapp://callback")
