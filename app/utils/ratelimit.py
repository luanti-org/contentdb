# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import ipaddress
from typing import List

from flask import request

from limits import parse
from limits.errors import StorageError
from limits.storage import RedisStorage
from limits.strategies import SlidingWindowCounterRateLimiter

from app import app, redis_client

# Shared by all web and worker processes, so limits hold across gunicorn workers.
# Counts events rather than rows, so deleting the thing that was made doesn't free up the limit.
# Uses the app's Redis connection pool rather than opening another.
storage = RedisStorage(app.config["REDIS_URL"], connection_pool=redis_client.connection_pool, wrap_exceptions=True)
_limiter = SlidingWindowCounterRateLimiter(storage)


class RateLimit:
	"""
	A rate limit on an action, which may have more than one window. For example,
	`RateLimit(f"comment/user:{user.id}", ["2 per minute", "10 per hour"])`.

	A rate limit with no windows is unlimited.

	If Redis is unavailable, actions are allowed.
	"""

	def __init__(self, key: str, limits: List[str]):
		self.key = key
		self.items = [parse(limit) for limit in limits]

	def test(self) -> bool:
		"""
		Whether the action is allowed now, without using up any of the limit
		"""
		try:
			return all(_limiter.test(item, self.key) for item in self.items)
		except StorageError:
			app.logger.warning("Unable to check rate limit %s", self.key, exc_info=True)
			return True

	def hit(self) -> bool:
		"""
		Records the action. Returns False, without recording, if any window is full.
		"""
		return self.test() and self.record()

	def record(self) -> bool:
		"""
		Records the action without checking first. A window that is already full isn't added to.
		Returns False if any window was full.
		"""
		try:
			# A list rather than a generator, so every window is recorded
			return all([_limiter.hit(item, self.key) for item in self.items])
		except StorageError:
			app.logger.warning("Unable to update rate limit %s", self.key, exc_info=True)
			return True


def hit_all(*limits: RateLimit) -> bool:
	"""
	Records the action against all the limits, but only if none of them are full. Returns False if any are full.
	"""
	if not all(limit.test() for limit in limits):
		return False

	# A list rather than a generator, so every limit is recorded
	return all([limit.record() for limit in limits])


def get_client_ip_key() -> str:
	"""
	Identifies the client's IP for rate limiting. IPv6 addresses are grouped by /64, as one client is usually
	given a whole /64.
	"""
	addr = request.remote_addr or "unknown"
	try:
		ip = ipaddress.ip_address(addr)
	except ValueError:
		return addr

	if isinstance(ip, ipaddress.IPv6Address):
		if ip.ipv4_mapped:
			return str(ip.ipv4_mapped)
		return str(ipaddress.ip_network(f"{ip}/64", strict=False))

	return str(ip)


def _get_email_ratelimits(email: str) -> List[RateLimit]:
	recipient = email.strip().lower()
	ip = get_client_ip_key()
	return [
		RateLimit(f"email/to:{recipient}/ip:{ip}", ["5 per hour"]),
		# Anyone can use this up, stopping emails to that address. It's high enough that doing so is the same
		# amount of email the limit is preventing.
		RateLimit(f"email/to:{recipient}", ["20 per day"]),
		RateLimit(f"email/ip:{ip}", ["10 per hour", "30 per day"]),
	]


def can_send_email(email: str) -> bool:
	"""
	Whether an email may be sent to `email` because of the current request, without recording anything.
	Use this to refuse a request early, then call `hit_email_ratelimit` when the email is sent.
	"""
	return all(limit.test() for limit in _get_email_ratelimits(email))


def hit_email_ratelimit(email: str) -> bool:
	"""
	Records an email being sent to `email` because of the current request. Returns False, without recording,
	if too many emails have been sent to that address or because of requests from this client.

	Call this before deciding which email to send, so the result doesn't reveal whether an account exists.
	"""
	return hit_all(*_get_email_ratelimits(email))
