# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import json
from flask import Blueprint

from .support import error

bp = Blueprint("api", __name__)


from . import tokens, endpoints


@bp.errorhandler(400)
@bp.errorhandler(401)
@bp.errorhandler(403)
@bp.errorhandler(404)
def handle_exception(e):
	"""Return JSON instead of HTML for HTTP errors."""
	# start with the correct headers and status code from the error
	response = e.get_response()
	# replace the body with JSON
	response.data = json.dumps({
		"success": False,
		"code": e.code,
		"name": e.name,
		"description": e.description,
	})
	response.content_type = "application/json"
	return response


@bp.route("/api/<path:path>")
def page_not_found(path):
	error(404, "Endpoint or method not found")
