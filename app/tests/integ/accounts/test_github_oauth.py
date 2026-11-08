# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Logging in, signing up, linking and re-authenticating with GitHub OAuth. GitHub is stubbed with http_stub.
"""

from urllib.parse import urlparse, parse_qs

import pytest

from app.models import db, User, UserRank, AuditLogEntry, UserSession
from ..factories import create_user, login_as, client_request, make_session_stale, get_user


TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"


def stub_github(http_stub, user_id=1234, login="octocat", status=200):
	http_stub.add("POST", TOKEN_URL, body="access_token=gho_token&token_type=bearer")
	if status == 200:
		http_stub.add("GET", USER_URL, json={"id": user_id, "login": login})
	else:
		http_stub.add("GET", USER_URL, status=status, json={"message": "Bad credentials"})


def start(client, next_url: str | None = None) -> str:
	"""
	Starts the flow, as clicking "Log in with GitHub" does, and returns the state to send back.
	"""
	rv = client_request(client, "GET", "/github/start/" + (f"?next={next_url}" if next_url else ""))
	assert rv.status_code == 302, rv.headers.get("Location")
	location = urlparse(rv.headers["Location"])
	assert location.netloc == "github.com"
	return parse_qs(location.query)["state"][0]


def callback(client, state: str | None, next_url: str | None = None, code: str | None = "code123"):
	params = []
	if code:
		params.append(f"code={code}")
	if state:
		params.append(f"state={state}")
	if next_url:
		params.append(f"next={next_url}")
	return client_request(client, "GET", "/github/callback/?" + "&".join(params))


def logged_in_user(client) -> User | None:
	with client.session_transaction() as sess:
		token = sess.get("_user_id")
	if token is None:
		return None
	from app.utils.misc import hash_token
	user_session = UserSession.query.filter_by(token_hash=hash_token(token)).first()
	return user_session.user if user_session else None


def test_sign_up(client, http_stub):
	stub_github(http_stub)

	rv = callback(client, start(client))

	assert rv.status_code == 302
	user = get_user("octocat")
	assert user.github_user_id == 1234
	assert user.github_username == "octocat"
	assert user.rank == UserRank.NEW_MEMBER
	assert user.email is None
	assert logged_in_user(client) == user
	assert AuditLogEntry.query.filter_by(title="Registered with GitHub, display name=octocat").count() == 1


def test_sign_up_with_taken_username(client, http_stub):
	create_user("octocat")
	stub_github(http_stub)

	rv = callback(client, start(client))

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/login/"
	assert User.query.filter_by(github_user_id=1234).count() == 0
	assert logged_in_user(client) is None


def test_log_in(client, http_stub):
	user = create_user("member", github_user_id=1234)
	stub_github(http_stub, login="renamed-on-github")

	rv = callback(client, start(client, "/packages/"), "/packages/")

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/"
	assert logged_in_user(client) == user
	# The GitHub username is updated, as it can change
	assert get_user("member").github_username == "renamed-on-github"
	assert AuditLogEntry.query.filter_by(title="Logged in using GitHub OAuth").count() == 1


def test_link_account(client, http_stub):
	user = create_user("member")
	login_as(client, user)
	stub_github(http_stub)

	rv = callback(client, start(client))

	assert rv.status_code == 302
	user = get_user("member")
	assert (user.github_user_id, user.github_username) == (1234, "octocat")
	assert AuditLogEntry.query.filter_by(title="Linked GitHub account octocat").count() == 1


def test_link_account_needs_fresh_session(client, http_stub):
	user = create_user("member")
	login_as(client, user, fresh=False)

	rv = client_request(client, "GET", "/github/start/")

	assert rv.status_code == 302
	assert rv.headers["Location"].startswith("/user/reauthenticate/")
	assert http_stub.calls == []
	assert get_user("member").github_user_id is None


def test_link_account_session_went_stale(client, http_stub):
	user = create_user("member")
	login_as(client, user)
	state = start(client)
	make_session_stale(user)
	stub_github(http_stub)

	rv = callback(client, state)

	assert rv.status_code == 302
	assert rv.headers["Location"].startswith("/user/reauthenticate/")
	assert get_user("member").github_user_id is None


def test_reauthenticate(client, http_stub):
	user = create_user("member", github_user_id=1234)
	login_as(client, user, fresh=False)
	state = start(client)
	stub_github(http_stub)

	rv = callback(client, state, "/user/settings/email/")

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/settings/email/"
	user_session = UserSession.query.filter_by(user_id=user.id).one()
	db.session.refresh(user_session)
	assert user_session.reauthenticated_at is not None
	assert AuditLogEntry.query.filter_by(title="Re-authenticated using GitHub OAuth").count() == 1


def test_github_linked_to_other_user(client, http_stub):
	create_user("other", github_user_id=1234)
	user = create_user("member", github_user_id=5678)
	login_as(client, user, fresh=False)
	state = start(client)
	stub_github(http_stub)

	rv = callback(client, state)

	assert rv.status_code == 302
	assert get_user("member").github_user_id == 5678
	assert get_user("other").github_user_id == 1234
	assert logged_in_user(client) == get_user("member")
	# Someone else's GitHub account doesn't prove who you are
	user_session = UserSession.query.filter_by(user_id=user.id).one()
	db.session.refresh(user_session)
	assert user_session.reauthenticated_at is None
	assert AuditLogEntry.query.filter_by(title="Re-authenticated using GitHub OAuth").count() == 0


def test_banned_user_cant_log_in(client, http_stub):
	create_user("member", UserRank.BANNED, github_user_id=1234)
	stub_github(http_stub)

	callback(client, start(client))

	# check_for_ban logs banned users out on their next request
	rv = client_request(client, "GET", "/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/login/"
	assert logged_in_user(client) is None


@pytest.mark.parametrize("case", ["missing", "wrong", "reused"])
def test_callback_needs_state_from_start(client, http_stub, case):
	"""
	Without a state check, another site could send someone to the callback with its own code, to log them in as
	someone else, or to link someone else's GitHub account to their ContentDB account.
	"""
	user = create_user("member")
	login_as(client, user)
	stub_github(http_stub)

	state: str | None = start(client)
	if case == "missing":
		state = None
	elif case == "wrong":
		state = "x" * 32
	elif case == "reused":
		assert callback(client, state).status_code == 302
		db.session.query(User).filter_by(username="member").update({"github_user_id": None, "github_username": None})
		db.session.commit()
		http_stub.calls.clear()

	rv = callback(client, state)

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/login/"
	# The code isn't exchanged for a token
	assert http_stub.calls == []
	assert get_user("member").github_user_id is None


def test_callback_without_code(client, http_stub):
	rv = callback(client, start(client), code=None)

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/login/"
	assert http_stub.calls == []


@pytest.mark.parametrize("next_url", ["https://evil.example/", "//evil.example/"])
def test_unsafe_next(client, http_stub, next_url):
	assert client_request(client, "GET", f"/github/start/?next={next_url}").status_code == 400


def test_non_int_github_id(client, http_stub):
	stub_github(http_stub, user_id="1234")

	rv = callback(client, start(client))

	assert rv.status_code == 400
	assert logged_in_user(client) is None
