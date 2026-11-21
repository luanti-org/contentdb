# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
A small client for Scaleway Transactional Email (TEM), used to find out which emails couldn't be delivered.

Sending is asynchronous: TEM accepts an email over SMTP, then delivers it later, retrying soft bounces for up to
72 hours. So delivery failures aren't seen when sending, and have to be read from the API.

API reference: https://www.scaleway.com/en/developers/api/transactional-email/
The field names here match the official Python SDK (scaleway.tem.v1alpha1).
"""

import datetime
from typing import Any, Iterator

import requests
from flask import current_app


API_URL = "https://api.scaleway.com/transactional-email/v1alpha1/regions/{region}"
PAGE_SIZE = 100
# A safety limit, so a misbehaving API can't loop forever
MAX_PAGES = 1000
TIMEOUT = (10, 60)


class ScalewayTEMError(Exception):
	pass


def is_configured() -> bool:
	return bool(current_app.config.get("SCALEWAY_TEM_SECRET_KEY") and current_app.config.get("SCALEWAY_TEM_PROJECT_ID"))


def is_blocklist_configured() -> bool:
	return is_configured() and bool(current_app.config.get("SCALEWAY_TEM_DOMAIN_ID"))


def format_datetime(value: datetime.datetime) -> str:
	"""
	Formats a naive UTC datetime as RFC 3339
	"""
	return value.replace(microsecond=0).isoformat() + "Z"


def _get_pages(path: str, params: dict[str, Any], key: str) -> Iterator[dict]:
	region = current_app.config.get("SCALEWAY_TEM_REGION") or "fr-par"
	url = API_URL.format(region=region) + path
	headers = {
		"Accept": "application/json",
		"X-Auth-Token": current_app.config["SCALEWAY_TEM_SECRET_KEY"],
	}

	for page in range(1, MAX_PAGES + 1):
		res = requests.get(url, params={**params, "page": page, "page_size": PAGE_SIZE}, headers=headers,
				timeout=TIMEOUT)
		if not res.ok:
			raise ScalewayTEMError(f"{path} returned {res.status_code}: {res.text[:500]}")

		items = res.json().get(key) or []
		yield from items

		if len(items) < PAGE_SIZE:
			return

	raise ScalewayTEMError(f"{path} returned more than {MAX_PAGES} pages")


def list_failed_emails(since: datetime.datetime) -> Iterator[dict]:
	"""
	Emails that TEM gave up on, created after `since`, oldest first.

	Each is a dict with fields including `mail_rcpt`, `status`, `flags`, `last_tries` and `created_at`.
	Note that `since` filters by when the email was created, not when it failed.
	"""
	params = {
		"project_id": current_app.config["SCALEWAY_TEM_PROJECT_ID"],
		"statuses": ["failed"],
		"since": format_datetime(since),
		"order_by": "created_at_asc",
	}
	return _get_pages("/emails", params, "emails")


def list_blocklists() -> Iterator[dict]:
	"""
	Addresses that TEM refuses to send to. Each is a dict with `email`, `type`, `custom`, `reason` and `ends_at`.
	"""
	params = {
		"domain_id": current_app.config["SCALEWAY_TEM_DOMAIN_ID"],
	}
	return _get_pages("/blocklists", params, "blocklists")


def parse_datetime(value: str | None) -> datetime.datetime | None:
	"""
	Parses an RFC 3339 timestamp from the API into a naive UTC datetime
	"""
	if not value:
		return None

	parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
	if parsed.tzinfo is not None:
		parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
	return parsed
