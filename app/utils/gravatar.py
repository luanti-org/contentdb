# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Opt-in Gravatar profile pictures, served through a proxy (thumbnails.gravatar).

Gravatar URLs contain a hash of the email address, which can be used to check guesses of it, so they're never
sent to browsers. Pages link to /thumbnails/gravatar/<user id>.png instead, and the server fetches the image.
"""

import hashlib
import hmac
from typing import TYPE_CHECKING

from flask import current_app, url_for

if TYPE_CHECKING:
	from app.models import User


GRAVATAR_SIZE = 256


def get_gravatar_version(email: str) -> str:
	"""
	Changes when the email does, to bust caches, without revealing anything about the email
	"""
	key = current_app.config["SECRET_KEY"].encode("utf-8")
	return hmac.new(key, b"gravatar:" + email.strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def get_gravatar_proxy_url(user: "User") -> str:
	assert user.email
	# Relative even outside a request, such as in tasks, where url_for would otherwise make it absolute.
	# User.get_profile_pic_url(absolute=True) makes it absolute.
	return url_for("thumbnails.gravatar", user_id=user.id, v=get_gravatar_version(user.email), _external=False)


def get_gravatar_url(email: str) -> str:
	"""
	The URL on Gravatar. Must only be requested by the server, never shown to users.
	`d=404` makes Gravatar return a 404 if there's no image, so the user's other profile picture can be used.
	"""
	email_hash = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
	return f"https://gravatar.com/avatar/{email_hash}?s={GRAVATAR_SIZE}&d=404&r=g"
