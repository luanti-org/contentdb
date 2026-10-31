# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Optional

from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature


# Unsubscribe links can't be revoked, so they expire instead.
# Expired links fall back to asking for the email address
UNSUBSCRIBE_TOKEN_MAX_AGE_S = 7 * 24 * 60 * 60


def _get_unsubscribe_serializer() -> URLSafeTimedSerializer:
	return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="unsubscribe")


def make_unsubscribe_token(sub_id: int) -> str:
	return _get_unsubscribe_serializer().dumps(sub_id)


# Returns the EmailSubscription id, or None if the token is invalid or has expired
def load_unsubscribe_token(token: str) -> Optional[int]:
	try:
		sub_id = _get_unsubscribe_serializer().loads(token, max_age=UNSUBSCRIBE_TOKEN_MAX_AGE_S)
	except BadSignature:
		return None

	return sub_id if isinstance(sub_id, int) else None
