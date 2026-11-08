# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import urllib.parse
from unittest.mock import MagicMock


from app import app
from app.blueprints.users import settings
from app.models import db, User, UserRank, APIToken, AuditLogEntry, UserEmailVerification
from app.utils.misc import hash_token
from ..factories import DEFAULT_PASSWORD, create_user, get_user, login_as, make_session_stale, client_request, \
	create_token, create_oauth_client
from ..utils import login, is_logged_in


def assert_reauth_redirect(rv, next_url: str | None = None):
	assert rv.status_code == 302, rv.status_code
	location = urllib.parse.urlparse(rv.headers["Location"])
	assert location.path == "/user/reauthenticate/"
	if next_url is not None:
		assert urllib.parse.parse_qs(location.query)["next"] == [next_url]


def test_login_is_fresh(client):
	create_user("member")
	assert is_logged_in(login(client, "member", DEFAULT_PASSWORD))

	rv = client_request(client, "GET", "/users/member/tokens/new/")
	assert rv.status_code == 200


def test_reauthenticate_with_password(client):
	create_user("member")
	login(client, "member", DEFAULT_PASSWORD)
	make_session_stale(get_user("member"))

	rv = client_request(client, "GET", "/users/member/tokens/new/")
	assert_reauth_redirect(rv, "/users/member/tokens/new/")

	rv = client_request(client, "GET", rv.headers["Location"])
	assert rv.status_code == 200
	assert b"For your security, you need to confirm it" in rv.data
	assert b'name="password"' in rv.data
	assert b"Confirm with GitHub" not in rv.data

	rv = client_request(client, "POST", "/user/reauthenticate/?next=/users/member/tokens/new/", data=dict(password="wrong password"))
	assert rv.status_code == 200
	assert b"Incorrect password" in rv.data
	assert_reauth_redirect(client_request(client, "GET", "/users/member/tokens/new/"))

	rv = client_request(client, "POST", "/user/reauthenticate/?next=/users/member/tokens/new/", data=dict(password=DEFAULT_PASSWORD))
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/users/member/tokens/new/"
	assert client_request(client, "GET", "/users/member/tokens/new/").status_code == 200

	user = User.query.filter_by(username="member").one()
	assert AuditLogEntry.query.filter_by(causer_id=user.id, title="Re-authenticated using password").count() == 1


def test_reauthenticate_rejects_unsafe_next(client):
	create_user("member")
	login(client, "member", DEFAULT_PASSWORD)
	make_session_stale(get_user("member"))

	rv = client_request(client, "POST", "/user/reauthenticate/?next=https://evil.example.com/", data=dict(password=DEFAULT_PASSWORD))
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/"


def test_reauthenticate_is_rate_limited(client):
	create_user("member")
	login(client, "member", DEFAULT_PASSWORD)
	make_session_stale(get_user("member"))

	for _ in range(10):
		rv = client_request(client, "POST", "/user/reauthenticate/", data=dict(password="wrong password"))
		assert b"Incorrect password" in rv.data

	rv = client_request(client, "POST", "/user/reauthenticate/", data=dict(password=DEFAULT_PASSWORD))
	assert b"Too many failed attempts" in rv.data
	assert_reauth_redirect(client_request(client, "GET", "/users/member/tokens/new/"))


def test_reauthenticate_page_for_github_only_user(client):
	user = create_user("member", password=None, github_user_id=1234)
	login_as(client, user, fresh=False)

	rv = client_request(client, "GET", "/user/reauthenticate/?next=/users/member/tokens/new/")
	assert rv.status_code == 200
	assert b'name="password"' not in rv.data
	assert b"Confirm with GitHub" in rv.data
	assert b"/github/start/?next=/users/member/tokens/new/" in rv.data

	# GitHub is already linked, so starting the OAuth flow is how they re-authenticate
	rv = client_request(client, "GET", "/github/start/?next=/users/member/tokens/new/")
	assert "/user/reauthenticate/" not in rv.headers["Location"]


def test_github_start_requires_fresh_session_to_link(client):
	create_user("member")
	login(client, "member", DEFAULT_PASSWORD)
	make_session_stale(get_user("member"))

	rv = client_request(client, "GET", "/github/start/?next=/users/member/settings/account/")
	assert_reauth_redirect(rv)
	next_url = urllib.parse.parse_qs(urllib.parse.urlparse(rv.headers["Location"]).query)["next"][0]
	assert next_url.startswith("/github/start/")


def test_switch_user_is_not_fresh(client):
	create_user("member")
	assert is_logged_in(login(client, "rubenwardy", "tuckfrump"))

	rv = client_request(client, "POST", "/admin/switchuser/", data=dict(username="member"))
	assert rv.status_code == 302

	# Now the member, but the admin can't do sensitive actions as them
	assert_reauth_redirect(client_request(client, "GET", "/users/member/tokens/new/"))


def test_email_change_requires_fresh_session(client, monkeypatch):
	monkeypatch.setattr(settings, "send_verify_email", MagicMock())
	create_user("member")
	login(client, "member", DEFAULT_PASSWORD)
	make_session_stale(get_user("member"))

	rv = client_request(client, "POST", "/users/member/settings/email/", data=dict(email="attacker@example.com"))
	assert_reauth_redirect(rv, "/users/member/settings/email/")
	assert UserEmailVerification.query.count() == 0

	# Other settings on the page don't need a fresh session
	rv = client_request(client, "POST", "/users/member/settings/email/", data=dict(email="member@example.com"))
	assert rv.status_code == 302
	assert "/user/reauthenticate/" not in rv.headers["Location"]


def test_post_redirects_back_to_referrer(client):
	user = create_user("member")
	token = create_token(user)[0]
	login(client, "member", DEFAULT_PASSWORD)
	make_session_stale(get_user("member"))

	referrer = f"{app.config['BASE_URL']}/users/member/tokens/{token.id}/edit/"
	rv = client_request(client, "POST", f"/users/member/tokens/{token.id}/reset/", headers={"Referer": referrer})
	assert_reauth_redirect(rv, referrer)

	# Referrers on other sites aren't used
	rv = client_request(client, "POST", f"/users/member/tokens/{token.id}/reset/",
			headers={"Referer": "https://evil.example.com/"})
	assert_reauth_redirect(rv, "/")


def member_actions(user: User):
	token = create_token(user)[0]
	create_oauth_client(user)
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
	user = create_user("member")
	actions = member_actions(user)
	login(client, "member", DEFAULT_PASSWORD)
	make_session_stale(get_user("member"))

	for method, url, data in actions:
		assert_reauth_redirect(client_request(client, method, url, data=data))

	db.session.expire_all()
	user = User.query.filter_by(username="member").one()
	assert user.pending_deletion is None
	assert APIToken.query.filter(APIToken.client_id.isnot(None)).count() == 0


def test_set_password_requires_fresh_session(client):
	create_user("member")
	login(client, "member", DEFAULT_PASSWORD)
	user = User.query.filter_by(username="member").one()
	user.password = None
	db.session.commit()
	make_session_stale(get_user("member"))

	assert_reauth_redirect(client_request(client, "GET", "/user/set-password/"), "/user/set-password/")


def test_admin_actions_require_fresh_session(client):
	member = create_user("member")
	ver = UserEmailVerification()
	ver.user = member
	ver.email = "new@example.com"
	ver.token_hash = hash_token("token")
	db.session.add(ver)
	db.session.commit()

	login(client, "rubenwardy", "tuckfrump")
	make_session_stale(get_user("rubenwardy"))

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
		assert_reauth_redirect(client_request(client, method, url, data=data))

	db.session.expire_all()
	member = User.query.filter_by(username="member").one()
	assert member.rank == UserRank.MEMBER
	assert member.email == "member@example.com"
	assert UserEmailVerification.query.count() == 1

	# Editing other fields with modtools doesn't need a fresh session
	rv = client_request(client, "POST", "/users/member/modtools/", data=dict(username="member", display_name="Member", rank="MEMBER"))
	assert rv.status_code == 302
	assert "/user/reauthenticate/" not in rv.headers["Location"]
