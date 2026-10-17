# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from app.default_data import populate_test_data
from app.models import db, Package, PackageState, PackageReview, User
from .utils import parse_json, count_queries
from .utils import client # noqa


def add_reviews(package: Package, ratings: list[int]):
	author = User.query.first()
	for rating in ratings:
		review = PackageReview()
		review.package = package
		review.author = author
		review.rating = rating
		db.session.add(review)


def test_scores(client):
	populate_test_data(db.session)
	food = Package.query.filter_by(name="food").one()
	add_reviews(food, [5, 4, 3, 1])
	add_reviews(Package.query.filter_by(name="food_sweet").one(), [2])
	db.session.commit()

	scores = {(x["author"], x["name"]): x for x in parse_json(client.get("/api/scores/").data)}
	approved = Package.query.filter_by(state=PackageState.APPROVED).all()
	assert len(scores) == len(approved)
	for package in approved:
		assert scores[(package.author.username, package.name)] == package.as_score_dict()

	assert scores[("rubenwardy", "food")]["reviews"] == {"positive": 2, "neutral": 1, "negative": 1}
	assert scores[("rubenwardy", "food_sweet")]["reviews"] == {"positive": 0, "neutral": 0, "negative": 1}


def test_scores_query_count_is_constant(client):
	populate_test_data(db.session)
	db.session.commit()
	client.get("/api/scores/?limit=1")

	one = count_queries(lambda: client.get("/api/scores/?limit=1"))
	all_ = count_queries(lambda: client.get("/api/scores/"))
	assert all_ == one
