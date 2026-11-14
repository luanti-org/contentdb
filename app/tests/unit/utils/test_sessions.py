# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os

import pytest
from babel import Locale

from app import app
from app.utils import sessions
from app.utils.sessions import describe_platform, describe_location


@pytest.fixture(autouse=True)
def request_context(monkeypatch):
	monkeypatch.setattr(sessions, "_reader", None)
	monkeypatch.setattr(sessions, "_logged_errors", set())
	monkeypatch.setattr(sessions, "get_locale", lambda: Locale.parse("en"))
	with app.test_request_context():
		yield


@pytest.mark.parametrize("user_agent, expected", [
	("Mozilla/5.0 (Android 14; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0", "Firefox Mobile on Android"),
	("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 "
		"Safari/537.36", "Chrome on Windows"),
	("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
		"Version/18.1 Mobile/15E148 Safari/604.1", "Mobile Safari on iOS"),
	("Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0", "Firefox on Linux"),
	("not a browser", None),
	("", None),
	(None, None),
])
def test_describe_platform(user_agent, expected):
	assert describe_platform(user_agent) == expected


class FakeReader:
	def __init__(self, records: dict[str, object]):
		self.records = records

	def get(self, ip: str):
		if ip == "invalid":
			raise ValueError("not an IP")
		return self.records.get(ip)


LONDON = {
	"city": {"names": {"en": "London", "de": "London", "pt-BR": "Londres"}},
	"country": {"names": {"en": "United Kingdom", "de": "Vereinigtes Königreich", "pt-BR": "Reino Unido"}},
}


@pytest.fixture
def reader(monkeypatch):
	fake = FakeReader({
		"203.0.113.1": LONDON,
		"203.0.113.2": {"country": {"names": {"en": "France"}}},
		"203.0.113.3": {"city": {"names": {"en": "Nowhere"}}},
		"203.0.113.4": {"continent": {"names": {"en": "Europe"}}},
	})
	monkeypatch.setattr(sessions, "_get_reader", lambda: fake)
	return fake


@pytest.mark.parametrize("ip, expected", [
	("203.0.113.1", "London, United Kingdom"),
	("203.0.113.2", "France"),
	# A city without a country isn't shown alone
	("203.0.113.3", None),
	("203.0.113.4", None),
	# Not in the database, such as a private address
	("10.0.0.1", None),
	("invalid", None),
	("", None),
	(None, None),
])
def test_describe_location(reader, ip, expected):
	assert describe_location(ip) == expected


@pytest.mark.parametrize("locale, expected", [
	("pt_BR", "Londres, Reino Unido"),
	("de", "London, Vereinigtes Königreich"),
	# Not in GeoLite2, so English
	("fr", "London, United Kingdom"),
	("pt_PT", "London, United Kingdom"),
])
def test_describe_location_uses_locale(reader, monkeypatch, locale, expected):
	monkeypatch.setattr(sessions, "get_locale", lambda: Locale.parse(locale))
	assert describe_location("203.0.113.1") == expected


def test_no_database_configured(monkeypatch):
	monkeypatch.setitem(app.config, "GEOIP_CITY_DATABASE", None)
	assert describe_location("203.0.113.1") is None


def test_missing_database_is_logged_once(monkeypatch, tmp_path):
	monkeypatch.setitem(app.config, "GEOIP_CITY_DATABASE", str(tmp_path / "missing.mmdb"))
	warnings = []
	monkeypatch.setattr(app.logger, "warning", lambda msg, **kwargs: warnings.append(msg))

	assert describe_location("203.0.113.1") is None
	assert describe_location("203.0.113.1") is None
	assert len(warnings) == 1


def test_invalid_database(monkeypatch, tmp_path):
	path = tmp_path / "bad.mmdb"
	path.write_bytes(b"not a database")
	monkeypatch.setitem(app.config, "GEOIP_CITY_DATABASE", str(path))
	monkeypatch.setattr(app.logger, "warning", lambda msg, **kwargs: None)

	assert describe_location("203.0.113.1") is None


def test_database_is_reopened_when_replaced(monkeypatch, tmp_path):
	path = tmp_path / "city.mmdb"
	path.write_bytes(b"v1")
	monkeypatch.setitem(app.config, "GEOIP_CITY_DATABASE", str(path))
	opened = []

	def open_database(p):
		opened.append(p)
		return FakeReader({"203.0.113.1": LONDON})

	monkeypatch.setattr(sessions.maxminddb, "open_database", open_database)

	assert describe_location("203.0.113.1") == "London, United Kingdom"
	assert describe_location("203.0.113.1") == "London, United Kingdom"
	assert opened == [str(path)]

	# Such as geoipupdate replacing the file
	path.write_bytes(b"v2")
	os.utime(path, (1, 1))
	assert describe_location("203.0.113.1") == "London, United Kingdom"
	assert opened == [str(path), str(path)]
