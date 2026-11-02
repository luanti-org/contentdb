# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import List

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
