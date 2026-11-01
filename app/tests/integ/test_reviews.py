# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from app.default_data import populate_test_data
from app.models import db, User, Package, PackageReview, PackageReviewVote, Thread
from app.utils.user import make_flask_login_password
from .utils import login
from .utils import client # noqa


def make_review(package: Package, author: User) -> PackageReview:
	review = PackageReview()
	review.package = package
	review.author = author
	review.rating = 5
	db.session.add(review)

	thread = Thread()
	thread.title = "Great mod"
	thread.package = package
	thread.review = review
	thread.author = author
	db.session.add(thread)

	db.session.commit()
	return review


def setup_review_vote(client):
	populate_test_data(db.session)
	voter = User.query.filter_by(username="rubenwardy").one()
	voter.password = make_flask_login_password("tuckfrump")
	db.session.commit()

	package = Package.query.filter_by(name="mesecons").one()
	review = make_review(package, User.query.filter_by(username="Shara").one())

	login(client, "rubenwardy", "tuckfrump")
	return review


def test_review_vote_redirects_to_thread_without_next_url(client):
	review = setup_review_vote(client)
	url = f"/packages/Jeija/mesecons/review/{review.id}/"

	rv = client.post(url, data=dict(is_positive="yes"))
	assert rv.status_code == 302
	assert rv.headers["Location"] == review.get_view_url()

	vote = PackageReviewVote.query.filter_by(review_id=review.id).one()
	assert vote.is_positive


def test_review_vote_redirects_to_next_url(client):
	review = setup_review_vote(client)
	url = f"/packages/Jeija/mesecons/review/{review.id}/?r=/packages/Jeija/mesecons/"

	rv = client.post(url, data=dict(is_positive="no"))
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/Jeija/mesecons/"


def test_review_vote_unknown_review(client):
	setup_review_vote(client)

	rv = client.post("/packages/Jeija/mesecons/review/9999/", data=dict(is_positive="yes"))
	assert rv.status_code == 404
