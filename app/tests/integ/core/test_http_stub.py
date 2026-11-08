# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest
import requests


def test_unexpected_requests_fail(http_stub):
	with pytest.raises(AssertionError, match="Unexpected HTTP request: GET https://example.com/"):
		requests.get("https://example.com/", timeout=5)


def test_responses_are_returned_in_order(http_stub):
	http_stub.add("POST", "https://example.com/api", status=500)
	http_stub.add("POST", "https://example.com/api", json={"ok": True})

	assert requests.post("https://example.com/api", timeout=5).status_code == 500
	res = requests.post("https://example.com/api", timeout=5)
	assert res.status_code == 200
	assert res.json() == {"ok": True}
	assert b"".join(res.iter_content(4)) == b'{"ok": true}'
	# The last response is repeated
	assert requests.post("https://example.com/api", timeout=5).json() == {"ok": True}
	assert [x[0] for x in http_stub.calls] == ["POST", "POST", "POST"]
