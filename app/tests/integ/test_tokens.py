# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import hmac
import json
import re
import time

from app.models import db, User, UserRank, APIToken, EmailSubscription, UserEmailVerification
from app.utils.misc import hash_token, random_string
from app.utils.tokens import get_github_webhook_secret, UNSUBSCRIBE_TOKEN_MAX_AGE_S
from app.utils.user import make_flask_login_password
from .utils import login, parse_json
from .utils import client # noqa


def make_user(username, rank, email=None):
	user = User(username)
	user.is_active = True
	user.email = email
	user.email_confirmed_at = datetime.datetime.now()
	user.password = make_flask_login_password("password123")
	user.rank = rank
	db.session.add(user)
	db.session.commit()
	return user


def create_api_token(client, username):
	rv = client.post(f"/users/{username}/tokens/new/", data=dict(name="Test", package=""), follow_redirects=True)
	assert rv.status_code == 200

	match = re.search(rb'readonly value="([0-9a-f]{32})"', rv.data)
	assert match
	return match.group(1).decode("utf-8")


def whoami(client, access_token):
	return client.get("/api/whoami/", headers={"Authorization": f"Bearer {access_token}"})


def test_api_token_hashed(client):
	make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	access_token = create_api_token(client, "member")

	token = APIToken.query.one()
	assert token.access_token_hash == hash_token(access_token)

	# Only shown once
	rv = client.get(f"/users/member/tokens/{token.id}/edit/")
	assert access_token.encode("utf-8") not in rv.data

	rv = whoami(client, access_token)
	assert rv.status_code == 200
	assert parse_json(rv.data)["username"] == "member"

	rv = whoami(client, token.access_token_hash)
	assert rv.status_code == 403


def test_api_token_reset(client):
	make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	old_token = create_api_token(client, "member")
	token = APIToken.query.one()

	rv = client.post(f"/users/member/tokens/{token.id}/reset/", follow_redirects=True)
	match = re.search(rb'readonly value="([0-9a-f]{32})"', rv.data)
	assert match
	new_token = match.group(1).decode("utf-8")

	assert whoami(client, old_token).status_code == 403
	assert whoami(client, new_token).status_code == 200


def post_github_webhook(client, url, key):
	data = json.dumps({"repository": {"full_name": "example/repo"}}).encode("utf-8")
	signature = hmac.new(key.encode("utf-8"), msg=data, digestmod="sha1").hexdigest()
	return client.post(url, data=data, content_type="application/json",
			headers={"X-Hub-Signature": f"sha1={signature}"})


def get_secret(token_id):
	db.session.expire_all()
	token = APIToken.query.get(token_id)
	assert token is not None
	return get_github_webhook_secret(token.id, token.access_token_hash)


def test_github_webhook_secret(client):
	make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	access_token = create_api_token(client, "member")
	token = APIToken.query.one()
	url = f"/github/webhook/{token.id}/"
	secret = get_secret(token.id)

	rv = client.get(f"/users/member/tokens/{token.id}/edit/")
	assert secret.encode("utf-8") in rv.data
	assert f"http://localhost:5124{url}".encode("utf-8") in rv.data

	# Valid signature, so it fails later on finding the package
	rv = post_github_webhook(client, url, secret)
	assert rv.status_code == 400
	assert b"Could not find package" in rv.data

	assert post_github_webhook(client, url, access_token).status_code == 401
	assert post_github_webhook(client, url, token.access_token_hash).status_code == 401
	assert post_github_webhook(client, f"/github/webhook/{token.id + 100}/", secret).status_code == 401

	rv = post_github_webhook(client, "/github/webhook/", secret)
	assert rv.status_code == 400
	assert b"needs to include the API token's id" in rv.data


def test_github_webhook_secret_changes_on_reset(client):
	make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	create_api_token(client, "member")
	token_id = APIToken.query.one().id
	url = f"/github/webhook/{token_id}/"
	old_secret = get_secret(token_id)

	client.post(f"/users/member/tokens/{token_id}/reset/")
	new_secret = get_secret(token_id)
	assert new_secret != old_secret

	assert post_github_webhook(client, url, old_secret).status_code == 401
	assert post_github_webhook(client, url, new_secret).status_code == 400


def test_github_webhook_rejects_other_tokens_secret(client):
	make_user("member", UserRank.MEMBER)
	login(client, "member", "password123")

	create_api_token(client, "member")
	create_api_token(client, "member")
	token_1, token_2 = APIToken.query.order_by(APIToken.id).all()

	rv = post_github_webhook(client, f"/github/webhook/{token_1.id}/", get_secret(token_2.id))
	assert rv.status_code == 401


def test_unsubscribe_signed_token(client):
	sub = EmailSubscription("test@example.com")
	db.session.add(sub)
	db.session.commit()

	rv = client.get(sub.url)
	assert rv.status_code == 200
	assert b'name="email"' not in rv.data

	rv = client.get(sub.url + "x")
	assert rv.status_code == 200
	assert b'name="email"' in rv.data
	assert b"invalid or has expired" in rv.data

	rv = client.get("/unsubscribe/?token=" + str(sub.id))
	assert b'name="email"' in rv.data

	rv = client.get("/unsubscribe/")
	assert b'name="email"' in rv.data
	assert b"invalid or has expired" not in rv.data


def test_unsubscribe_link_expires(client, monkeypatch):
	sub = EmailSubscription("test@example.com")
	db.session.add(sub)
	db.session.commit()

	url = sub.url
	monkeypatch.setattr(time, "time", lambda now=time.time(): now + UNSUBSCRIBE_TOKEN_MAX_AGE_S + 60)

	rv = client.get(url)
	assert b'name="email"' in rv.data
	assert b"invalid or has expired" in rv.data


def make_email_verification(user, email):
	ver = UserEmailVerification()
	ver.user = user
	ver.email = email
	ver.token_hash = hash_token(random_string(32))
	db.session.add(ver)
	db.session.commit()
	return ver.id


def test_modtools_verify_email(client):
	user = make_user("member", UserRank.MEMBER, "old@example.com")
	make_user("mod", UserRank.MODERATOR)
	ver_id = make_email_verification(user, "new@example.com")

	login(client, "mod", "password123")
	rv = client.post(f"/users/member/modtools/verify-email/{ver_id}/", follow_redirects=True)
	assert rv.status_code == 200

	db.session.expire_all()
	assert User.query.filter_by(username="member").one().email == "new@example.com"
	assert UserEmailVerification.query.get(ver_id) is None


def test_modtools_verify_email_requires_mod(client):
	user = make_user("member", UserRank.MEMBER, "old@example.com")
	make_user("other", UserRank.MEMBER)
	ver_id = make_email_verification(user, "new@example.com")

	login(client, "other", "password123")
	rv = client.post(f"/users/member/modtools/verify-email/{ver_id}/")
	assert rv.status_code == 403

	db.session.expire_all()
	assert User.query.filter_by(username="member").one().email == "old@example.com"
	assert UserEmailVerification.query.get(ver_id) is not None
