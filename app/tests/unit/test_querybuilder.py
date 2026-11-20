# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""QueryBuilder argument handling that doesn't need the database"""

from urllib.parse import parse_qsl

import pytest
from flask import request
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import HTTPException

from app import app
from app.querybuilder import QueryBuilder


def make_args(query_string: str) -> MultiDict:
	return MultiDict(parse_qsl(query_string, keep_blank_values=True))


@pytest.mark.parametrize("query_string,message", [
	("type=nope", "Unknown type"),
	("sort=nope", "Unknown sort"),
	("order=sideways", "order must be asc or desc"),
	("limit=abc", "limit must be an integer"),
	("protocol_version=abc", "protocol_version must be an integer"),
	("sort=collection", "sort=collection needs a collection"),
	("collection=nope", "Unable to find that collection"),
])
def test_errors_are_400_with_message(query_string, message):
	with app.test_request_context("/api/packages/"):
		with pytest.raises(HTTPException) as e:
			QueryBuilder(make_args(query_string), emit_http_errors=True)

		response = e.value.get_response()
		assert response.status_code == 400
		assert message in response.get_data(as_text=True)


def test_without_http_errors_falls_back():
	with app.test_request_context("/"):
		qb = QueryBuilder(make_args("sort=nope&order=sideways&limit=abc&protocol_version=abc"), emit_http_errors=False)
		assert qb.order_by is None
		assert qb.order_dir == "desc"
		assert qb.limit is None
		assert qb.version is None
		assert not qb.match_nothing

		qb = QueryBuilder(make_args("sort=collection"), emit_http_errors=False)
		assert qb.order_by is None


@pytest.mark.parametrize("query_string,match_nothing", [
	("type=nope", True),
	("type=nope&type=mod", False),
	("collection=nope", True),
	("type=mod", False),
])
def test_without_http_errors_stale_references_match_nothing(query_string, match_nothing):
	with app.test_request_context("/"):
		qb = QueryBuilder(make_args(query_string), emit_http_errors=False)
		assert qb.match_nothing == match_nothing


def test_amp_check_only_applies_to_request_args():
	with app.test_request_context("/?type=mod&amp;sort=score"):
		with pytest.raises(HTTPException) as e:
			QueryBuilder(request.args)
		assert e.value.code == 400

		# Args from elsewhere, such as a homepage widget's stored query, aren't affected by the page's URL
		qb = QueryBuilder(make_args("type=mod"), emit_http_errors=False)
		assert [t.name for t in qb.types] == ["MOD"]
