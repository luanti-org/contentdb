# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Fixtures shared by all integration tests. Model and login helpers are in factories.py.
"""

import http
import io
import json as jsonlib
import time
from typing import Any

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from app import app
from app.models import User
from app.tasks import celery
from app.utils.ratelimit import storage as ratelimit_storage
from .utils import recreate_db


# Saved before http_stub patches it, so Mailpit can still be reached
_real_session_request = requests.Session.request


@pytest.fixture
def client():
	"""
	A test client with a freshly populated database. Most integration tests need this.
	CSRF is disabled, so forms can be posted without a token.
	"""
	with app.app_context():
		app.config["TESTING"] = True
		app.config['WTF_CSRF_ENABLED'] = False

		recreate_db()
		assert User.query.count() == 2
		ratelimit_storage.reset()

		with app.test_client() as client:
			yield client

		app.config["TESTING"] = False
		app.config['WTF_CSRF_ENABLED'] = True


class HttpStub:
	"""
	Replaces outgoing HTTP requests made with `requests`. Responses are registered with `add`, and any other
	request fails the test, so tests never reach the internet.
	"""

	def __init__(self):
		self._responses: dict[tuple[str, str], list[requests.Response]] = {}
		self.calls: list[tuple[str, str, dict[str, Any]]] = []

	def add(self, method: str, url: str, status: int = 200, json: Any = None, body: bytes | str = b"",
			headers: dict[str, str] | None = None):
		"""
		Adds a response for `method` and `url` (exact match, including the query string). Adding several for the
		same request returns them in order, then keeps returning the last.
		"""
		if json is not None:
			body = jsonlib.dumps(json)
			headers = {"Content-Type": "application/json", **(headers or {})}
		if isinstance(body, str):
			body = body.encode("utf-8")

		response = requests.Response()
		response.status_code = status
		response.reason = http.HTTPStatus(status).phrase
		response.headers = CaseInsensitiveDict(headers or {})
		response.url = url
		response._content = body
		# Marks the content as read, so iter_content() works on it. It's private, so isn't in the type stubs.
		setattr(response, "_content_consumed", True)
		response.raw = io.BytesIO(body)
		response.encoding = "utf-8"
		self._responses.setdefault((method.upper(), url), []).append(response)

	def request(self, method: str, url: str, **kwargs) -> requests.Response:
		self.calls.append((method.upper(), url, kwargs))
		responses = self._responses.get((method.upper(), url))
		if not responses:
			raise AssertionError(f"Unexpected HTTP request: {method.upper()} {url}")

		return responses.pop(0) if len(responses) > 1 else responses[0]


@pytest.fixture
def http_stub(monkeypatch) -> HttpStub:
	"""
	Stubs all requests made with the `requests` library. See HttpStub.
	"""
	stub = HttpStub()
	monkeypatch.setattr(requests.Session, "request", lambda session, method, url, **kwargs: stub.request(method, url, **kwargs))
	return stub


class Mailpit:
	"""
	Reads emails sent to Mailpit, the SMTP server in the test stack (docker-compose.test.yml).
	"""

	BASE_URL = "http://mailpit:8025/api/v1"

	def _request(self, method: str, path: str) -> requests.Response:
		res = _real_session_request(requests.Session(), method, f"{self.BASE_URL}{path}", timeout=5)
		res.raise_for_status()
		return res

	def clear(self):
		self._request("DELETE", "/messages")

	def messages(self) -> list[dict[str, Any]]:
		return self._request("GET", "/messages").json()["messages"]

	def messages_to(self, email: str) -> list[dict[str, Any]]:
		return [x for x in self.messages() if any(to["Address"] == email for to in x["To"])]

	def wait_for(self, email: str, timeout: float = 10) -> dict[str, Any]:
		"""
		Waits for an email to arrive for `email`, returning the newest. Needed when a Celery worker sends it.
		"""
		deadline = time.monotonic() + timeout
		while True:
			messages = self.messages_to(email)
			if messages:
				return messages[0]
			if time.monotonic() > deadline:
				raise AssertionError(f"No email arrived for {email}")
			time.sleep(0.1)

	def get_text(self, message: dict[str, Any]) -> str:
		return self._request("GET", f"/message/{message['ID']}").json()["Text"]

	def get_html(self, message: dict[str, Any]) -> str:
		return self._request("GET", f"/message/{message['ID']}").json()["HTML"]


@pytest.fixture
def mailpit() -> Mailpit:
	"""
	Empties Mailpit before the test. Combine with eager_tasks so that emails are sent during the request.
	"""
	client = Mailpit()
	client.clear()
	return client


@pytest.fixture
def eager_tasks():
	"""
	Runs Celery tasks inline when they're queued with .delay() or .apply_async(), rather than on the test stack's
	worker. The worker only loads the code when the stack starts, so it may be running an old version.
	"""
	celery.conf.task_always_eager = True
	celery.conf.task_eager_propagates = True
	yield
	celery.conf.task_always_eager = False
	celery.conf.task_eager_propagates = False
