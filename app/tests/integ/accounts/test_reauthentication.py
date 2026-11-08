# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
import urllib.parse
from unittest.mock import MagicMock

from flask import g

from app import app
from app.blueprints.users import settings
from app.models import db, User, UserRank, UserSession, APIToken, OAuthClient, AuditLogEntry, UserEmailVerification
from app.utils.misc import hash_token, random_string
from app.utils.user import make_flask_login_password
from ..utils import login, is_logged_in


PASSWORD = "VYjNnjdDPhCVUZx"


def make_member(username: str = "member", password: str | None = PASSWORD, github_user_id: int | None = None) -> User:
	user = User(username, active=True, email=f"{username}@example.com",
			password=make_flask_login_password(password) if password else None)
	user.rank = UserRank.MEMBER
	user.github_user_id = github_user_id
	user.github_username = username if github_user_id else None
	db.session.add(user)
	db.session.commit()
	return user


def make_stale(username: str):
	user = User.query.filter_by(username=username).one()
	stale = datetime.datetime.utcnow() - UserSession.FRESH_FOR - datetime.timedelta(minutes=1)
	UserSession.query.filter_by(user_id=user.id).update({"reauthenticated_at": stale})
	db.session.commit()


def request(client, method: str, url: str, **kwargs):
	# The client fixture keeps one app context for the whole test, so Flask-Login's cached user in g would
	# otherwise survive between requests
	g.pop("_login_user", None)
	return client.open(url, method=method, **kwargs)


def assert_reauth_redirect(rv, next_url: str | None = None):
	assert rv.status_code == 302, rv.status_code
	location = urllib.parse.urlparse(rv.headers["Location"])
	assert location.path == "/user/reauthenticate/"
	if next_url is not None:
		assert urllib.parse.parse_qs(location.query)["next"] == [next_url]


def make_token(owner: User) -> APIToken:
	token = APIToken()
	token.name = "test"
	token.owner = owner
	token.access_token_hash = hash_token(random_string(32))
	db.session.add(token)
	db.session.commit()
	return token


def make_oauth_client(owner: User) -> OAuthClient:
	oauth_client = OAuthClient()
	oauth_client.id = "testclient"
	oauth_client.secret_hash = hash_token("secret")
	oauth_client.title = "Test App"
	oauth_client.redirect_url = "https://example.com/callback/"
	oauth_client.approved = True
	oauth_client.owner = owner
	db.session.add(oauth_client)
	db.session.commit()
	return oauth_client


def test_login_is_fresh(client):
	make_member()
	assert is_logged_in(login(client, "member", PASSWORD))

	rv = request(client, "GET", "/users/member/tokens/new/")
	assert rv.status_code == 200


def test_reauthenticate_with_password(client):
	make_member()
	login(client, "member", PASSWORD)
	make_stale("member")

	rv = request(client, "GET", "/users/member/tokens/new/")
	assert_reauth_redirect(rv, "/users/member/tokens/new/")

	rv = request(client, "GET", rv.headers["Location"])
	assert rv.status_code == 200
	assert b"For your security, you need to confirm it" in rv.data
	assert b'name="password"' in rv.data
	assert b"Confirm with GitHub" not in rv.data

	rv = request(client, "POST", "/user/reauthenticate/?next=/users/member/tokens/new/", data=dict(password="wrong password"))
	assert rv.status_code == 200
	assert b"Incorrect password" in rv.data
	assert_reauth_redirect(request(client, "GET", "/users/member/tokens/new/"))

	rv = request(client, "POST", "/user/reauthenticate/?next=/users/member/tokens/new/", data=dict(password=PASSWORD))
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/users/member/tokens/new/"
	assert request(client, "GET", "/users/member/tokens/new/").status_code == 200

	user = User.query.filter_by(username="member").one()
	assert AuditLogEntry.query.filter_by(causer_id=user.id, title="Re-authenticated using password").count() == 1


def test_reauthenticate_rejects_unsafe_next(client):
	make_member()
	login(client, "member", PASSWORD)
	make_stale("member")

	rv = request(client, "POST", "/user/reauthenticate/?next=https://evil.example.com/", data=dict(password=PASSWORD))
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/"


def test_reauthenticate_is_rate_limited(client):
	make_member()
	login(client, "member", PASSWORD)
	make_stale("member")

	for _ in range(10):
		rv = request(client, "POST", "/user/reauthenticate/", data=dict(password="wrong password"))
		assert b"Incorrect password" in rv.data

	rv = request(client, "POST", "/user/reauthenticate/", data=dict(password=PASSWORD))
	assert b"Too many failed attempts" in rv.data
	assert_reauth_redirect(request(client, "GET", "/users/member/tokens/new/"))


def login_with_session(client, user: User, fresh: bool):
	# For users without a password, such as GitHub-only users
	token = random_string(64)
	user_session = UserSession()
	user_session.user = user
	user_session.token_hash = hash_token(token)
	user_session.reauthenticated_at = datetime.datetime.utcnow() if fresh else None
	db.session.add(user_session)
	db.session.commit()
	with client.session_transaction() as sess:
		sess["_user_id"] = token


def test_reauthenticate_page_for_github_only_user(client):
	user = make_member(password=None, github_user_id=1234)
	login_with_session(client, user, fresh=False)

	rv = request(client, "GET", "/user/reauthenticate/?next=/users/member/tokens/new/")
	assert rv.status_code == 200
	assert b'name="password"' not in rv.data
	assert b"Confirm with GitHub" in rv.data
	assert b"/github/start/?next=/users/member/tokens/new/" in rv.data

	# GitHub is already linked, so starting the OAuth flow is how they re-authenticate
	rv = request(client, "GET", "/github/start/?next=/users/member/tokens/new/")
	assert "/user/reauthenticate/" not in rv.headers["Location"]


def test_github_start_requires_fresh_session_to_link(client):
	make_member()
	login(client, "member", PASSWORD)
	make_stale("member")

	rv = request(client, "GET", "/github/start/?next=/users/member/settings/account/")
	assert_reauth_redirect(rv)
	next_url = urllib.parse.parse_qs(urllib.parse.urlparse(rv.headers["Location"]).query)["next"][0]
	assert next_url.startswith("/github/start/")


def test_switch_user_is_not_fresh(client):
	make_member()
	assert is_logged_in(login(client, "rubenwardy", "tuckfrump"))

	rv = request(client, "POST", "/admin/switchuser/", data=dict(username="member"))
	assert rv.status_code == 302

	# Now the member, but the admin can't do sensitive actions as them
	assert_reauth_redirect(request(client, "GET", "/users/member/tokens/new/"))


def test_email_change_requires_fresh_session(client, monkeypatch):
	monkeypatch.setattr(settings, "send_verify_email", MagicMock())
	make_member()
	login(client, "member", PASSWORD)
	make_stale("member")

	rv = request(client, "POST", "/users/member/settings/email/", data=dict(email="attacker@example.com"))
	assert_reauth_redirect(rv, "/users/member/settings/email/")
	assert UserEmailVerification.query.count() == 0

	# Other settings on the page don't need a fresh session
	rv = request(client, "POST", "/users/member/settings/email/", data=dict(email="member@example.com"))
	assert rv.status_code == 302
	assert "/user/reauthenticate/" not in rv.headers["Location"]


def test_post_redirects_back_to_referrer(client):
	user = make_member()
	token = make_token(user)
	login(client, "member", PASSWORD)
	make_stale("member")

	referrer = f"{app.config['BASE_URL']}/users/member/tokens/{token.id}/edit/"
	rv = request(client, "POST", f"/users/member/tokens/{token.id}/reset/", headers={"Referer": referrer})
	assert_reauth_redirect(rv, referrer)

	# Referrers on other sites aren't used
	rv = request(client, "POST", f"/users/member/tokens/{token.id}/reset/",
			headers={"Referer": "https://evil.example.com/"})
	assert_reauth_redirect(rv, "/")


def member_actions(user: User):
	token = make_token(user)
	make_oauth_client(user)
	authorize_url = "/oauth/authorize/?response_type=code&client_id=testclient&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback%2F"
	return [
		("GET", "/users/member/tokens/new/", None),
		("POST", f"/users/member/tokens/{token.id}/reset/", None),
		("GET", "/users/member/apps/new/", None),
		("POST", "/users/member/apps/testclient/reset-secret/", None),
		("GET", authorize_url, None),
		("POST", authorize_url, dict(action="authorize")),
		("GET", "/users/member/delete/", None),
		("POST", "/users/member/delete/", dict(username="member")),
		("POST", "/users/member/settings/account/disconnect-github/", None),
	]


def test_member_actions_require_fresh_session(client):
	user = make_member()
	actions = member_actions(user)
	login(client, "member", PASSWORD)
	make_stale("member")

	for method, url, data in actions:
		assert_reauth_redirect(request(client, method, url, data=data))

	db.session.expire_all()
	user = User.query.filter_by(username="member").one()
	assert user.pending_deletion is None
	assert APIToken.query.filter(APIToken.client_id.isnot(None)).count() == 0


def test_set_password_requires_fresh_session(client):
	make_member()
	login(client, "member", PASSWORD)
	user = User.query.filter_by(username="member").one()
	user.password = None
	db.session.commit()
	make_stale("member")

	assert_reauth_redirect(request(client, "GET", "/user/set-password/"), "/user/set-password/")


def test_admin_actions_require_fresh_session(client):
	member = make_member()
	ver = UserEmailVerification()
	ver.user = member
	ver.email = "new@example.com"
	ver.token_hash = hash_token("token")
	db.session.add(ver)
	db.session.commit()

	login(client, "rubenwardy", "tuckfrump")
	make_stale("rubenwardy")

	actions = [
		("GET", "/admin/switchuser/", None),
		("POST", "/admin/switchuser/", dict(username="member")),
		("POST", "/admin/", dict(action="delete_inactive_users")),
		("POST", "/admin/users/delete/", dict(selected=["member"], confirm="1")),
		("GET", "/users/member/delete/", None),
		("POST", "/users/member/delete/", {"delete": "Delete"}),
		("POST", "/users/member/modtools/set-email/", dict(email="attacker@example.com")),
		("POST", f"/users/member/modtools/verify-email/{ver.id}/", None),
		("POST", "/users/member/modtools/unblock-password/", None),
		("POST", "/users/member/modtools/", dict(username="member", display_name="member", rank="MODERATOR")),
	]
	for method, url, data in actions:
		assert_reauth_redirect(request(client, method, url, data=data))

	db.session.expire_all()
	member = User.query.filter_by(username="member").one()
	assert member.rank == UserRank.MEMBER
	assert member.email == "member@example.com"
	assert UserEmailVerification.query.count() == 1

	# Editing other fields with modtools doesn't need a fresh session
	rv = request(client, "POST", "/users/member/modtools/", data=dict(username="member", display_name="Member", rank="MEMBER"))
	assert rv.status_code == 302
	assert "/user/reauthenticate/" not in rv.headers["Location"]
