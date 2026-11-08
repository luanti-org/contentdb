# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Private threads and unapproved reviews must not leak through listings, pages or the API.
"""

import pytest

from app.models import db, User, UserRank, PackageReview
from ..factories import create_user, create_package, create_thread, create_reply, create_review, login_as, \
	client_request


PUBLIC = "PublicThreadTitle"
PRIVATE = "PrivateThreadTitle"


def setup_threads():
	owner = create_user("owner")
	author = create_user("author")
	create_user("stranger")
	create_user("approver", UserRank.APPROVER)
	maintainer = create_user("maintainer")
	package = create_package("pkg", owner, maintainers=[maintainer])
	create_thread(author, package, PUBLIC)
	private = create_thread(author, package, PRIVATE, private=True)
	return package, private


def view_as(client, username: str | None, url: str):
	if username is not None:
		login_as(client, User.query.filter_by(username=username).one())
	return client_request(client, "GET", url)


@pytest.mark.parametrize("url", ["/threads/", "/packages/owner/pkg/threads/"])
@pytest.mark.parametrize("username,sees_private", [
	(None, False),
	("stranger", False),
	# The thread list only shows private threads to staff, even to the thread's author
	("author", False),
	("approver", True),
])
def test_thread_list_hides_private_threads(client, url, username, sees_private):
	setup_threads()

	rv = view_as(client, username, url)
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert PUBLIC in html
	assert (PRIVATE in html) == sees_private


@pytest.mark.parametrize("username,sees_private", [
	(None, False),
	("stranger", False),
	("author", True),
	("owner", True),
	("approver", True),
])
def test_package_page_hides_private_threads(client, username, sees_private):
	setup_threads()

	rv = view_as(client, username, "/packages/owner/pkg/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert PUBLIC in html
	assert (PRIVATE in html) == sees_private


@pytest.mark.parametrize("username,status", [
	(None, 404),
	("stranger", 404),
	("author", 200),
	("owner", 200),
	("maintainer", 200),
	("approver", 200),
])
def test_view_private_thread(client, username, status):
	_, private = setup_threads()

	rv = view_as(client, username, f"/threads/{private.id}/")
	assert rv.status_code == status
	assert (PRIVATE in rv.data.decode("utf-8")) == (status == 200)


def test_cant_subscribe_to_private_thread(client):
	_, private = setup_threads()
	stranger = User.query.filter_by(username="stranger").one()
	login_as(client, stranger)

	rv = client_request(client, "POST", f"/threads/{private.id}/subscribe/")
	assert rv.status_code == 404

	db.session.refresh(private)
	assert stranger not in private.watchers


@pytest.mark.parametrize("username,sees_private", [
	(None, False),
	("stranger", False),
	("author", True),
	("approver", True),
])
def test_user_comments_hide_private_replies(client, username, sees_private):
	package, private = setup_threads()
	author = User.query.filter_by(username="author").one()
	create_reply(private, author, "PrivateReplyText")
	public = create_thread(create_user("other"), package, "Other")
	create_reply(public, author, "PublicReplyText")

	rv = view_as(client, username, "/users/author/comments/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "PublicReplyText" in html
	assert ("PrivateReplyText" in html) == sees_private


APPROVED_TEXT = "ApprovedReviewText"
UNAPPROVED_TEXT = "UnapprovedReviewText"


def setup_reviews():
	owner = create_user("owner")
	package = create_package("pkg", owner)
	create_review(create_user("reviewer"), package, rating=5, comment=APPROVED_TEXT)
	create_review(create_user("spammer"), package, rating=1, approved=False, comment=UNAPPROVED_TEXT)
	create_user("stranger")
	create_user("moderator", UserRank.MODERATOR)
	return package


@pytest.mark.parametrize("url", [
	"/reviews/",
	"/api/reviews/",
	"/api/packages/owner/pkg/reviews/",
	"/api/packages/owner/pkg/for-client/reviews/?formspec_version=7",
])
def test_unapproved_reviews_hidden(client, url):
	setup_reviews()

	rv = client_request(client, "GET", url)
	assert rv.status_code == 200
	text = rv.data.decode("utf-8")
	assert APPROVED_TEXT in text
	assert UNAPPROVED_TEXT not in text
	assert "spammer" not in text


@pytest.mark.parametrize("username,sees_unapproved", [
	(None, False),
	("stranger", False),
	("owner", False),
	("spammer", True),
	("moderator", True),
])
def test_package_page_hides_unapproved_reviews(client, username, sees_unapproved):
	setup_reviews()

	rv = view_as(client, username, "/packages/owner/pkg/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert APPROVED_TEXT in html
	assert (UNAPPROVED_TEXT in html) == sees_unapproved


def test_review_counts_leave_out_unapproved_reviews(client):
	"""
	Unapproved reviews may be spam held for moderation, so mustn't affect the counts shown on the package page,
	the homepage or the API.
	"""
	package = setup_reviews()
	create_review(create_user("spammer2"), package, rating=5, approved=False)
	assert PackageReview.query.filter_by(package=package).count() == 3

	assert package.get_review_summary() == [1, 0, 0]

	rv = client_request(client, "GET", "/api/scores/")
	assert rv.json is not None
	scores = next(x for x in rv.json if x["name"] == "pkg")
	assert scores["reviews"] == {"positive": 1, "neutral": 0, "negative": 0}

	rv = client_request(client, "GET", "/api/packages/owner/pkg/for-client/?formspec_version=7")
	assert rv.json is not None
	assert rv.json["reviews"] == {"positive": 1, "neutral": 0, "negative": 0}

	rv = client_request(client, "GET", "/packages/owner/pkg/")
	assert "+1 / 0 / -0" in rv.data.decode("utf-8")
