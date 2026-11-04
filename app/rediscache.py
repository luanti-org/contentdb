# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import json

from . import redis_client
from .models import Package

# This file acts as a facade between the rest of the code and redis,
# and also means that the rest of the code avoids knowing about `app`


EXPIRY_TIME_S = 2*7*24*60*60  # 2 weeks


def make_download_key(ip: str, package: Package):
	return "{}/{}/{}".format(ip, package.author.username, package.name)


def make_view_key(ip: str, package: Package):
	return "view/{}/{}/{}".format(ip, package.author.username, package.name)


def set_temp_key(key, v):
	redis_client.set(key, v, ex=EXPIRY_TIME_S)


def check_and_set_temp_key(key, v):
	return redis_client.set(key, v, ex=EXPIRY_TIME_S, nx=True)


def has_key(key):
	return redis_client.exists(key)


def increment_key(key):
	redis_client.incrby(key, 1)


def get_key(key, default=None):
	return redis_client.get(key) or default


DOWNLOAD_EVENTS_KEY = "download_events"
DOWNLOAD_EVENT_REASONS = {"new", "dependency", "update"}


def increment_download_event(reason: str | None, is_luanti: bool):
	"""
	Counts a download event for the contentdb_download_events_total metric.
	Label values are restricted to a fixed set to bound cardinality, as reason is user-supplied.
	The hash must only ever be incremented: Prometheus treats any decrease as a counter reset.
	"""
	reason = reason if reason in DOWNLOAD_EVENT_REASONS else "other"
	platform = "luanti" if is_luanti else "other"
	redis_client.hincrby(DOWNLOAD_EVENTS_KEY, f"{reason}:{platform}", 1)


def get_download_events() -> list[tuple[str, str, int]]:
	"""Returns a list of (reason, platform, count)"""
	ret = []
	for field, value in redis_client.hgetall(DOWNLOAD_EVENTS_KEY).items():
		field = field.decode() if isinstance(field, bytes) else field
		reason, _, platform = field.partition(":")
		ret.append((reason, platform, int(value)))
	return sorted(ret)


def get_json_key(key, default=None):
	value = redis_client.get(key)
	return json.loads(value) if value is not None else default


def set_json_key(key, value, expiry_s):
	redis_client.set(key, json.dumps(value), ex=expiry_s)
