# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import urllib.parse as urlparse

from app.models import db, User, UserRank, OAuthClient, APIToken
from app.utils.misc import hash_token
from app.utils.user import make_flask_login_password
from .utils import login, parse_json
from .utils import client # noqa


def make_user(username, rank):
	user = User(username)
	user.is_active = True
	user.email_confirmed_at = datetime.datetime.now()
	user.password = make_flask_login_password("password123")
	user.rank = rank
	db.session.add(user)
	db.session.commit()
	return user


def make_oauth_client(owner, redirect_url="https://example.com/callback/"):
	oauth_client = OAuthClient()
	oauth_client.id = "testclient"
	oauth_client.secret = "secret"
	oauth_client.title = "Test App"
	oauth_client.redirect_url = redirect_url
	oauth_client.approved = True
	oauth_client.verified = True
	oauth_client.owner = owner
	db.session.add(oauth_client)
	db.session.commit()
	return oauth_client


def edit_oauth_client(client, owner, redirect_url):
	return client.post(f"/users/{owner.username}/apps/testclient/edit/", data=dict(
		title="Test App",
		description="",
		redirect_url=redirect_url,
		app_type="server",
	), follow_redirects=True)


def get_oauth_client():
	db.session.expire_all()
	return OAuthClient.query.get("testclient")


def test_oauth_create_rejects_invalid_redirect_url(client):
	user = make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	for redirect_url in ["javascript:alert(1)", "http://example.com/callback/", "https://example.com/#frag"]:
		rv = client.post("/users/member/apps/new/", data=dict(
			title="Test App",
			description="",
			redirect_url=redirect_url,
			app_type="server",
		), follow_redirects=True)
		assert b"Redirect URL must use https://" in rv.data
		assert OAuthClient.query.filter_by(owner=user).count() == 0

	rv = client.post("/users/member/apps/new/", data=dict(
		title="Test App",
		description="",
		redirect_url="https://example.com/callback/",
		app_type="server",
	), follow_redirects=True)
	assert b"Redirect URL must use https://" not in rv.data
	oauth_client = OAuthClient.query.filter_by(owner=user).one()
	assert oauth_client.redirect_url == "https://example.com/callback/"
	assert not oauth_client.approved


def test_oauth_edit_redirect_url_resets_approval(client):
	user = make_user("member", UserRank.MEMBER)
	make_oauth_client(user)
	login(client, "member", "password123")

	rv = edit_oauth_client(client, user, "https://evil.example.com/callback/")
	assert b"requires staff to approve your application again" in rv.data

	oauth_client = get_oauth_client()
	assert oauth_client.redirect_url == "https://evil.example.com/callback/"
	assert not oauth_client.approved
	assert not oauth_client.verified


def test_oauth_edit_without_redirect_url_change_keeps_approval(client):
	user = make_user("member", UserRank.MEMBER)
	make_oauth_client(user)
	login(client, "member", "password123")

	rv = edit_oauth_client(client, user, "https://example.com/callback/")
	assert b"requires staff to approve your application again" not in rv.data

	oauth_client = get_oauth_client()
	assert oauth_client.approved
	assert oauth_client.verified


def test_oauth_edit_invalid_redirect_url_is_not_saved(client):
	user = make_user("member", UserRank.MEMBER)
	make_oauth_client(user)
	login(client, "member", "password123")

	rv = edit_oauth_client(client, user, "javascript:alert(1)")
	assert b"Redirect URL must use https://" in rv.data

	oauth_client = get_oauth_client()
	assert oauth_client.redirect_url == "https://example.com/callback/"
	assert oauth_client.approved


def test_oauth_editor_edit_redirect_url_keeps_approval(client):
	user = make_user("editor", UserRank.EDITOR)
	make_oauth_client(user)
	login(client, "editor", "password123")

	edit_oauth_client(client, user, "https://new.example.com/callback/")

	oauth_client = get_oauth_client()
	assert oauth_client.redirect_url == "https://new.example.com/callback/"
	assert oauth_client.approved
	assert oauth_client.verified


def authorize(client, oauth_client):
	rv = client.post("/oauth/authorize/", query_string=dict(
		response_type="code",
		client_id=oauth_client.id,
		redirect_uri=oauth_client.redirect_url,
		state="abc",
	), data=dict(action="authorize"))
	assert rv.status_code == 302
	location = urlparse.urlparse(rv.headers["Location"])
	query = dict(urlparse.parse_qsl(location.query))
	assert query["state"] == "abc"
	return query["code"]


def redeem(client, client_secret, code):
	return client.post("/oauth/token/", data=dict(
		client_id="testclient",
		client_secret=client_secret,
		code=code,
	))


def test_oauth_flow(client):
	owner = make_user("owner", UserRank.MEMBER)
	oauth_client = make_oauth_client(owner)
	make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	code = authorize(client, oauth_client)
	token = APIToken.query.filter_by(client_id="testclient").one()
	assert token.auth_code == code

	# Not usable until the code is redeemed
	assert APIToken.query.filter_by(access_token_hash=hash_token(code)).count() == 0

	assert redeem(client, "wrong", code).status_code == 400

	rv = redeem(client, "secret", code)
	assert rv.status_code == 200
	access_token = parse_json(rv.data)["access_token"]

	db.session.expire_all()
	token = APIToken.query.filter_by(client_id="testclient").one()
	assert token.access_token_hash == hash_token(access_token)
	assert token.auth_code is None

	rv = client.get("/api/whoami/", headers={"Authorization": f"Bearer {access_token}"})
	assert rv.status_code == 200
	assert parse_json(rv.data)["username"] == "member"

	# Code can only be used once
	assert redeem(client, "secret", code).status_code == 400

	# Authorizing again doesn't revoke the old token until the new code is redeemed
	code = authorize(client, oauth_client)
	rv = client.get("/api/whoami/", headers={"Authorization": f"Bearer {access_token}"})
	assert rv.status_code == 200

	rv = redeem(client, "secret", code)
	assert rv.status_code == 200
	new_access_token = parse_json(rv.data)["access_token"]

	rv = client.get("/api/whoami/", headers={"Authorization": f"Bearer {access_token}"})
	assert rv.status_code == 403
	rv = client.get("/api/whoami/", headers={"Authorization": f"Bearer {new_access_token}"})
	assert rv.status_code == 200


def test_oauth_get_authorize_does_not_revoke_token(client):
	owner = make_user("owner", UserRank.MEMBER)
	oauth_client = make_oauth_client(owner)
	make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	access_token = parse_json(redeem(client, "secret", authorize(client, oauth_client)).data)["access_token"]

	# A plain GET, like a link or image elsewhere, only issues a new code
	rv = client.get("/oauth/authorize/", query_string=dict(
		response_type="code",
		client_id=oauth_client.id,
		redirect_uri=oauth_client.redirect_url,
	))
	assert rv.status_code == 302

	rv = client.get("/api/whoami/", headers={"Authorization": f"Bearer {access_token}"})
	assert rv.status_code == 200
