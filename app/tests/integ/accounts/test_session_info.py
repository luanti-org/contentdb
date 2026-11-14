# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
The IP address and user agent recorded for login sessions, and how they're shown on the account page.
"""

import datetime

import pytest

from app.models import db, UserSession, UserRank
from app.utils import sessions
from ..factories import create_user, login_as, client_request, DEFAULT_PASSWORD


IP = "203.0.113.5"
FIREFOX_ANDROID = "Mozilla/5.0 (Android 14; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0"
CHROME_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " \
		"Chrome/131.0.0.0 Safari/537.36"


def from_client(ip: str, user_agent: str) -> dict:
	# The test stack trusts one proxy, so X-Forwarded-For gives the client's IP
	return {"headers": {"X-Forwarded-For": ip, "User-Agent": user_agent}}


class FakeReader:
	def __init__(self, records: dict[str, dict]):
		self.records = records

	def get(self, ip: str):
		return self.records.get(ip)


@pytest.fixture
def geoip(monkeypatch):
	reader = FakeReader({
		IP: {
			"city": {"names": {"en": "London"}},
			"country": {"names": {"en": "United Kingdom"}},
		},
	})
	monkeypatch.setattr(sessions, "_get_reader", lambda: reader)
	return reader


def test_login_records_ip_and_user_agent(client):
	create_user("alice")

	rv = client_request(client, "POST", "/user/login/", data={"username": "alice", "password": DEFAULT_PASSWORD},
			**from_client(IP, FIREFOX_ANDROID))

	assert rv.status_code == 302
	user_session = UserSession.query.one()
	assert user_session.ip_address == IP
	assert user_session.user_agent == FIREFOX_ANDROID


def test_long_user_agent_is_truncated(client):
	create_user("alice")
	user_agent = FIREFOX_ANDROID + "x" * 1000

	client_request(client, "POST", "/user/login/", data={"username": "alice", "password": DEFAULT_PASSWORD},
			**from_client(IP, user_agent))

	assert UserSession.query.one().user_agent == user_agent[:UserSession.USER_AGENT_MAX_LENGTH]


def test_using_session_updates_ip_and_user_agent(client):
	login_as(client, create_user("alice"))
	user_session = UserSession.query.one()

	# Recent sessions aren't written to on every request
	recent = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
	user_session.last_used_at = recent
	db.session.commit()
	client_request(client, "GET", "/", **from_client(IP, FIREFOX_ANDROID))
	db.session.expire_all()
	user_session = UserSession.query.one()
	assert (user_session.ip_address, user_session.user_agent) == (None, None)

	# Updated along with last_used_at
	user_session.last_used_at = datetime.datetime.utcnow() - datetime.timedelta(days=1)
	db.session.commit()
	client_request(client, "GET", "/", **from_client(IP, FIREFOX_ANDROID))
	db.session.expire_all()
	user_session = UserSession.query.one()
	assert (user_session.ip_address, user_session.user_agent) == (IP, FIREFOX_ANDROID)
	assert user_session.last_used_at > recent


def test_account_page_shows_platform_and_location(client, geoip):
	alice = create_user("alice")
	login_as(client, alice)
	current = UserSession.query.one()
	current.ip_address = IP
	current.user_agent = FIREFOX_ANDROID

	other = UserSession()
	other.user = alice
	other.token_hash = "b" * 64
	other.ip_address = "198.51.100.7"
	other.user_agent = CHROME_WINDOWS
	db.session.add(other)
	db.session.commit()

	rv = client_request(client, "GET", "/users/alice/settings/account/")

	html = rv.get_data(as_text=True)
	assert "Firefox Mobile on Android" in html
	assert "London, United Kingdom" in html
	# Not in the GeoIP database, so shown without a location
	assert "Chrome on Windows" in html
	assert html.count("London, United Kingdom") == 1
	assert html.count("This device") == 1
	# The IP itself is never shown
	assert IP not in html
	assert "198.51.100.7" not in html


def test_account_page_without_session_info(client):
	login_as(client, create_user("alice"))

	rv = client_request(client, "GET", "/users/alice/settings/account/")

	assert "Unknown device" in rv.get_data(as_text=True)


def test_moderator_doesnt_see_this_device(client, geoip):
	alice = create_user("alice")
	login_as(client, alice)
	user_session = UserSession.query.one()
	user_session.ip_address = IP
	user_session.user_agent = FIREFOX_ANDROID
	db.session.commit()

	login_as(client, create_user("mod", rank=UserRank.MODERATOR))

	rv = client_request(client, "GET", "/users/alice/settings/account/")

	html = rv.get_data(as_text=True)
	assert "Firefox Mobile on Android" in html
	assert "London, United Kingdom" in html
	assert "This device" not in html
	assert IP not in html
