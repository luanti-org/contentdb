# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

from app.models import db, User, UserRank, OAuthClient
from app.utils.user import make_flask_login_password
from .utils import login
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
