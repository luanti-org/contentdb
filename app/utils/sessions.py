# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Describes where a login session is used from, for the user's account page.
"""

import os
import threading
from typing import Any, Optional

import maxminddb
import user_agents
from flask import current_app
from flask_babel import gettext, get_locale


UNKNOWN_FAMILY = "Other"


def describe_platform(user_agent: Optional[str]) -> Optional[str]:
	"""
	Returns the browser and operating system, such as "Firefox on Android", or None if neither is known.
	"""
	if not user_agent:
		return None

	parsed = user_agents.parse(user_agent)
	browser = parsed.browser.family if parsed.browser.family != UNKNOWN_FAMILY else None
	os_name = parsed.os.family if parsed.os.family != UNKNOWN_FAMILY else None
	if browser and os_name:
		return gettext("%(browser)s on %(os)s", browser=browser, os=os_name)

	return browser or os_name


_reader_lock = threading.Lock()
# (path, modification time, reader) of the open database
_reader: Optional[tuple[str, float, maxminddb.Reader]] = None
_logged_errors: set[str] = set()


def _log_once(path: str, message: str):
	if path not in _logged_errors:
		_logged_errors.add(path)
		current_app.logger.warning(message, exc_info=True)


def _get_reader() -> Optional[maxminddb.Reader]:
	"""
	Opens the GeoLite2 City database at GEOIP_CITY_DATABASE, reopening it when the file is replaced, such as by
	geoipupdate. Returns None if it isn't configured or can't be read.
	"""
	global _reader

	path = current_app.config.get("GEOIP_CITY_DATABASE")
	if not path:
		return None

	try:
		mtime = os.stat(path).st_mtime
	except OSError:
		_log_once(path, f"Unable to find the GeoIP database at {path}")
		return None

	with _reader_lock:
		if _reader is None or _reader[0] != path or _reader[1] != mtime:
			try:
				# The old reader isn't closed, as another thread may be using it. It's closed when garbage collected.
				_reader = (path, mtime, maxminddb.open_database(path))
			except (OSError, maxminddb.InvalidDatabaseError):
				_log_once(path, f"Unable to open the GeoIP database at {path}")
				return None

		return _reader[2]


def _get_name(record: Any) -> Optional[str]:
	"""
	Returns the name in a GeoLite2 record in the user's language, falling back to English.
	"""
	if not isinstance(record, dict) or not isinstance(record.get("names"), dict):
		return None

	names = record["names"]
	locale = get_locale()
	languages = []
	if locale is not None:
		# GeoLite2 uses names like "pt-BR" and "zh-CN"
		if locale.territory:
			languages.append(f"{locale.language}-{locale.territory}")
		languages.append(locale.language)
	languages.append("en")

	for language in languages:
		name = names.get(language)
		if isinstance(name, str) and name:
			return name

	return None


def describe_location(ip_address: Optional[str]) -> Optional[str]:
	"""
	Returns the approximate location of an IP address, such as "London, United Kingdom", or None if it's unknown.
	The lookup uses a local database, so the IP address isn't sent anywhere.
	"""
	if not ip_address:
		return None

	reader = _get_reader()
	if reader is None:
		return None

	try:
		record = reader.get(ip_address)
	except ValueError:
		# Not a valid IP address
		return None

	if not isinstance(record, dict):
		return None

	city = _get_name(record.get("city"))
	country = _get_name(record.get("country"))
	if city and country:
		return gettext("%(city)s, %(country)s", city=city, country=country)

	return country
