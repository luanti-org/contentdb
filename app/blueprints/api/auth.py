# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from functools import wraps

from flask import request, abort

from app.models import APIToken
from .support import error


def is_api_authd(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		token = None

		value = request.headers.get("authorization")
		if value is None:
			pass
		elif value[0:7].lower() == "bearer ":
			access_token = value[7:]
			if len(access_token) < 10:
				error(400, "API token is too short")

			token = APIToken.query.filter_by(access_token=access_token).first()
			if token is None:
				error(403, "Unknown API token")
		else:
			error(403, "Unsupported authentication method")

		return f(token=token, *args, **kwargs)

	return decorated_function
