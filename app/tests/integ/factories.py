# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Helpers for creating test data and logging in.

`create_*` functions add the object, commit, and return it, so it's visible to requests made with the test client.
Pass the returned objects to other factories to build up a scenario.
"""

import datetime
import io
import zipfile
from typing import Any

from flask import g
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from app.models import db, User, UserRank, UserSession, Package, PackageState, PackageType, PackageRelease, \
	ReleaseState, PackageScreenshot, Thread, ThreadReply, PackageReview, PackageReviewVote, APIToken, OAuthClient, \
	Collection, CollectionPackage, Report, ReportCategory
from app.utils.misc import hash_token, random_string
from app.utils.user import make_flask_login_password
from .utils import make_package


DEFAULT_PASSWORD = "VYjNnjdDPhCVUZx"

_DEFAULT: Any = object()


def create_user(username: str, rank: UserRank = UserRank.MEMBER, password: str | None = DEFAULT_PASSWORD,
		email: str | None = _DEFAULT, github_user_id: int | None = None, active: bool = True) -> User:
	"""
	`email` defaults to `<username>@example.com`. Pass None for a user without an email.
	"""
	if email is _DEFAULT:
		email = f"{username.lower()}@example.com"

	user = User(username, active=active, email=email,
			password=make_flask_login_password(password) if password else None)
	user.rank = rank
	if github_user_id is not None:
		user.github_user_id = github_user_id
		user.github_username = username
	db.session.add(user)
	db.session.commit()
	return user


def get_user(username: str) -> User:
	db.session.expire_all()
	return User.query.filter_by(username=username).one()


def login_as(client: FlaskClient, user: User, fresh: bool = True):
	"""
	Logs `user` in on the test client, without going through the login form. Works for users without a password,
	and doesn't use up login rate limits. With fresh=False, sensitive actions need re-authenticating.
	"""
	token = random_string(64)
	user_session = UserSession()
	user_session.user = user
	user_session.token_hash = hash_token(token)
	user_session.reauthenticated_at = datetime.datetime.utcnow() if fresh else None
	db.session.add(user_session)
	db.session.commit()

	with client.session_transaction() as sess:
		sess["_user_id"] = token
	g.pop("_login_user", None)


def make_session_stale(user: User):
	"""
	Makes the user's sessions need re-authenticating before sensitive actions.
	"""
	stale = datetime.datetime.utcnow() - UserSession.FRESH_FOR - datetime.timedelta(minutes=1)
	UserSession.query.filter_by(user_id=user.id).update({"reauthenticated_at": stale})
	db.session.commit()


def client_request(client: FlaskClient, method: str, url: str, **kwargs) -> TestResponse:
	"""
	Makes a request with the test client. Use this when a test makes several requests, possibly as different users.

	The client fixture keeps one app context for the whole test, so Flask-Login's cached user in `g` would otherwise
	survive from the previous request.
	"""
	g.pop("_login_user", None)
	return client.open(url, method=method, **kwargs)


def create_package(name: str, author: User, state: PackageState = PackageState.APPROVED,
		type: PackageType = PackageType.MOD, maintainers: list[User] | None = None) -> Package:
	package = make_package(name, author)
	package.state = state
	package.type = type
	package.maintainers.append(author)
	for maintainer in maintainers or []:
		package.maintainers.append(maintainer)
	db.session.commit()
	return package


def create_release(package: Package, name: str = "1.0", approved: bool = True) -> PackageRelease:
	release = PackageRelease()
	release.package = package
	release.name = name
	release.title = name
	release.upload_path = f"/uploads/{random_string(10)}.zip"
	release.state = ReleaseState.APPROVED if approved else ReleaseState.UNAPPROVED
	db.session.add(release)
	db.session.commit()
	return release


def create_screenshot(package: Package, title: str = "Screenshot", approved: bool = True) -> PackageScreenshot:
	screenshot = PackageScreenshot()
	screenshot.package = package
	screenshot.title = title
	screenshot.upload_path = f"/uploads/{random_string(10)}.png"
	screenshot.approved = approved
	screenshot.width = 1920
	screenshot.height = 1080
	db.session.add(screenshot)
	db.session.commit()
	return screenshot


def create_thread(author: User, package: Package | None = None, title: str = "Hello", private: bool = False,
		comment: str = "First comment") -> Thread:
	"""
	Creates a thread with a first reply by its author, as the site does.
	"""
	thread = Thread()
	thread.title = title
	thread.author = author
	thread.package = package
	thread.private = private
	db.session.add(thread)
	db.session.commit()
	create_reply(thread, author, comment)
	return thread


def create_reply(thread: Thread, author: User, comment: str = "A reply") -> ThreadReply:
	reply = ThreadReply()
	reply.thread = thread
	reply.author = author
	reply.comment = comment
	db.session.add(reply)
	db.session.commit()
	return reply


def create_review(author: User, package: Package, rating: int = 5, approved: bool = True,
		comment: str = "First comment") -> PackageReview:
	"""
	Creates a review with its thread.
	"""
	review = PackageReview()
	review.package = package
	review.author = author
	review.rating = rating
	review.approved = approved
	db.session.add(review)

	thread = create_thread(author, package, f"Review by {author.username}", private=not approved, comment=comment)
	thread.review = review
	package.recalculate_score()
	db.session.commit()
	return review


def create_review_vote(review: PackageReview, user: User, is_positive: bool = True) -> PackageReviewVote:
	vote = PackageReviewVote()
	vote.review = review
	vote.user = user
	vote.is_positive = is_positive
	db.session.add(vote)
	review.update_score()
	db.session.commit()
	return vote


def create_token(owner: User, package: Package | None = None, name: str = "test") -> tuple[APIToken, str]:
	"""
	Returns the token and its raw access token, for use in an `Authorization: Bearer` header.
	"""
	access_token = random_string(32)
	token = APIToken()
	token.name = name
	token.owner = owner
	token.package = package
	token.access_token_hash = hash_token(access_token)
	db.session.add(token)
	db.session.commit()
	return token, access_token


def create_oauth_client(owner: User, client_id: str = "testclient", approved: bool = True,
		redirect_url: str = "https://example.com/callback/") -> OAuthClient:
	oauth_client = OAuthClient()
	oauth_client.id = client_id
	oauth_client.title = f"App {client_id}"
	oauth_client.secret_hash = hash_token("secret")
	oauth_client.redirect_url = redirect_url
	oauth_client.approved = approved
	oauth_client.owner = owner
	db.session.add(oauth_client)
	db.session.commit()
	return oauth_client


def create_collection(author: User, packages: list[Package] | None = None, name: str = "favorites",
		private: bool = False) -> Collection:
	collection = Collection()
	collection.author = author
	collection.name = name
	collection.title = name.title()
	collection.short_description = f"{name.title()} collection"
	collection.private = private
	db.session.add(collection)
	for i, package in enumerate(packages or []):
		item = CollectionPackage()
		item.package = package
		item.collection = collection
		item.order = i
		db.session.add(item)
	db.session.commit()
	return collection


def create_report(user: User | None, thread: Thread | None = None, category: ReportCategory = ReportCategory.SPAM,
		title: str = "Spam") -> Report:
	report = Report()
	report.id = random_string(24)
	report.user = user
	report.thread = thread
	report.category = category
	report.title = title
	report.message = "Report message"
	db.session.add(report)
	db.session.commit()
	return report


def make_zip(files: dict[str, str]) -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		for name, content in files.items():
			zf.writestr(name, content)
	return buf.getvalue()


def make_mod_zip(name: str = "pkg") -> bytes:
	"""
	A minimal valid mod, which passes the release checks for a mod package called `name`.
	"""
	return make_zip({
		f"{name}/mod.conf": f"name = {name}\n",
		f"{name}/init.lua": "",
		f"{name}/LICENSE.txt": "MIT",
	})
