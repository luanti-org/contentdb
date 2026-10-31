# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import pytest

from app.default_data import populate_test_data
from app.models import db, User, UserRank, Package, PackageState, Collection, CollectionPackage, APIToken, OAuthClient
from app.utils.misc import hash_token, random_string
from app.utils.user import make_flask_login_password
from .utils import login
from .utils import client # noqa


PASSWORD = "VYjNnjdDPhCVUZx"


def make_user(username: str) -> User:
	user = User(username, active=True, email=f"{username}@example.com",
			password=make_flask_login_password(PASSWORD))
	user.rank = UserRank.MEMBER
	db.session.add(user)
	return user


def make_collection(owner: User, private: bool) -> Collection:
	populate_test_data(db.session)

	unapproved = Package.query.filter_by(name="awards").one()
	unapproved.state = PackageState.WIP

	collection = Collection()
	collection.author = owner
	collection.name = "secret"
	collection.title = "Secret collection"
	collection.short_description = "Hidden description"
	collection.private = private
	db.session.add(collection)

	for i, name in enumerate(["mesecons", "awards"]):
		item = CollectionPackage()
		item.collection = collection
		item.package = Package.query.filter_by(name=name).one()
		item.order = i
		item.description = f"Note about {name}"
		db.session.add(item)

	db.session.commit()
	return collection


def clone(client):
	return client.post("/collections/owner/secret/clone/")


def get_clones(user: User) -> list[Collection]:
	return Collection.query.filter(Collection.author == user, Collection.name.like("secret%")).all()


def test_clone_private_collection_by_other_user(client):
	make_user("cloner")
	make_collection(make_user("owner"), private=True)
	login(client, "cloner", PASSWORD)

	assert clone(client).status_code == 404
	assert get_clones(User.query.filter_by(username="cloner").one()) == []


def test_clone_public_collection_hides_unapproved_packages(client):
	make_user("cloner")
	make_collection(make_user("owner"), private=False)
	login(client, "cloner", PASSWORD)

	assert clone(client).status_code == 302

	clones = get_clones(User.query.filter_by(username="cloner").one())
	assert len(clones) == 1
	assert clones[0].private
	assert [x.package.name for x in clones[0].items] == ["mesecons"]


def test_clone_own_private_collection(client):
	owner = make_user("owner")
	make_collection(owner, private=True)
	login(client, "owner", PASSWORD)

	assert clone(client).status_code == 302

	clones = [x for x in get_clones(owner) if x.name != "secret"]
	assert len(clones) == 1
	assert sorted(x.package.name for x in clones[0].items) == ["awards", "mesecons"]


def test_clone_requires_login(client):
	make_collection(make_user("owner"), private=False)

	rv = clone(client)
	assert rv.status_code == 302
	assert "/user/login/" in rv.headers["Location"]


def make_token(owner: User, kind: str) -> str:
	token = APIToken()
	token.name = kind
	token.owner = owner
	access_token = random_string(32)
	token.access_token_hash = hash_token(access_token)

	if kind == "oauth":
		oauth_client = OAuthClient()
		oauth_client.id = random_string(24)
		oauth_client.title = "Third party app"
		oauth_client.secret_hash = hash_token(random_string(32))
		oauth_client.redirect_url = "https://example.com/callback"
		oauth_client.owner = make_user("app_developer")
		oauth_client.approved = True
		db.session.add(oauth_client)
		token.client = oauth_client
	elif kind == "package":
		token.package = Package.query.filter_by(name="mesecons").one()

	db.session.add(token)
	db.session.commit()
	return access_token


def api_view(client, access_token: str | None = None):
	headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
	return client.get("/api/collections/owner/secret/", headers=headers)


def test_api_private_collection_with_account_token(client):
	owner = make_user("owner")
	make_collection(owner, private=True)
	access_token = make_token(owner, "account")

	rv = api_view(client, access_token)
	assert rv.status_code == 200
	assert sorted(x["package"]["name"] for x in rv.json["items"]) == ["awards", "mesecons"]


@pytest.mark.parametrize("kind", ["oauth", "package"])
def test_api_private_collection_with_limited_token(client, kind):
	owner = make_user("owner")
	make_collection(owner, private=True)
	access_token = make_token(owner, kind)

	assert api_view(client, access_token).status_code == 404


@pytest.mark.parametrize("kind", ["oauth", "package"])
def test_api_public_collection_with_limited_token(client, kind):
	owner = make_user("owner")
	make_collection(owner, private=False)
	access_token = make_token(owner, kind)

	rv = api_view(client, access_token)
	assert rv.status_code == 200
	assert [x["package"]["name"] for x in rv.json["items"]] == ["mesecons"]


def test_api_private_collection_anonymous(client):
	make_collection(make_user("owner"), private=True)

	assert api_view(client).status_code == 404
