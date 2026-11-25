# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
A cookie that lets members skip the bot check (Anubis's proof of work) in front of ContentDB.

Anubis only checks that the cookie is present, so ContentDB has to reject requests where it isn't valid: signed by
ContentDB, not expired, and for the logged-in user, who must be a member or above. Otherwise, anyone could set the
cookie to get past Anubis.
"""

import datetime
from typing import Optional

from flask import current_app, request, redirect
from werkzeug import Response
from flask_login import current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature

from app.models import UserRank


COOKIE_NAME = "cdb_bot_check_bypass"
MIN_RANK = UserRank.MEMBER
MAX_AGE = datetime.timedelta(days=30)

# Reissued when older than this, so the cookie doesn't expire while the user is active
REFRESH_AFTER = datetime.timedelta(days=1)


def _get_serializer() -> URLSafeTimedSerializer:
	return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="bot-check-bypass")


def make_bypass_token(user_id: int) -> str:
	return _get_serializer().dumps(user_id)


def _is_allowed() -> bool:
	return current_user.is_authenticated and current_user.rank.at_least(MIN_RANK)


def _get_token_age() -> Optional[datetime.timedelta]:
	"""
	Returns the age of the request's cookie, or None if it's not valid for the current user.
	"""
	token = request.cookies.get(COOKIE_NAME)
	if not token or not _is_allowed():
		return None

	try:
		user_id, signed_at = _get_serializer().loads(token, max_age=int(MAX_AGE.total_seconds()),
				return_timestamp=True)
	except BadSignature:
		return None

	if user_id != current_user.id:
		return None

	return datetime.datetime.now(datetime.timezone.utc) - signed_at


def _delete_cookie(response: Response):
	response.delete_cookie(COOKIE_NAME, secure=True, httponly=True, samesite="Lax")


def reject_invalid_cookie() -> Optional[Response]:
	"""
	before_request hook. Must run after the user is loaded and bans are checked.

	A request with a cookie that isn't valid didn't go through Anubis, so isn't served. Instead, it's redirected to
	the same URL with the cookie deleted. A browser will then go through Anubis, such as when the session has ended.
	307 keeps the method and body.
	"""
	if COOKIE_NAME not in request.cookies or _get_token_age() is not None:
		return None

	response = redirect(request.full_path if request.query_string else request.path, 307)
	_delete_cookie(response)
	return response


def update_cookie(response: Response) -> Response:
	"""
	after_request hook. Sets the cookie for members and above, and deletes it for everyone else.
	"""
	if _is_allowed():
		age = _get_token_age()
		if age is None or age > REFRESH_AFTER:
			response.set_cookie(COOKIE_NAME, make_bypass_token(current_user.id), max_age=MAX_AGE,
					secure=True, httponly=True, samesite="Lax")
	elif COOKIE_NAME in request.cookies:
		_delete_cookie(response)

	return response
