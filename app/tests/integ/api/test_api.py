# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

from app.default_data import populate_test_data
from app.models import db, Package, PackageState, DashboardWidgetType
from ..factories import create_collection, create_dashboard, create_package, create_release, create_user
from ..utils import parse_json, validate_package_list


def test_packages_empty(client):
	"""Start with a blank database."""

	rv = client.get("/api/packages/")
	assert parse_json(rv.data) == []


def test_packages_with_contents(client):
	"""Start with a test database."""

	populate_test_data(db.session)
	db.session.commit()

	rv = client.get("/api/packages/")

	packages = parse_json(rv.data)

	assert len(packages) > 0
	assert len(packages) == Package.query.filter_by(state=PackageState.APPROVED).count()

	validate_package_list(packages)


# def test_packages_with_query(client):
# 	"""Start with a test database."""
#
# 	populate_test_data(db.session)
# 	db.session.commit()
#
# 	rv = client.get("/api/packages/?q=food")
#
# 	packages = parse_json(rv.data)
#
# 	assert len(packages) == 2
#
# 	validate_package_list(packages)
#
# 	assert (packages[0]["name"] == "food" and packages[1]["name"] == "food_sweet") or \
# 		(packages[1]["name"] == "food" and packages[0]["name"] == "food_sweet")


def test_dependencies(client):
	"""Start with a test database."""

	populate_test_data(db.session)
	db.session.commit()

	deps = parse_json(client.get("/api/packages/rubenwardy/food_sweet/dependencies/").data)
	deps = deps["rubenwardy/food_sweet"]

	assert len(deps) == 1
	assert not deps[0]["is_optional"]
	assert len(deps[0]["packages"]) == 1
	assert deps[0]["packages"][0] == "rubenwardy/food"


def test_dashboards(client):
	"""utils/extract_translations.py reads widget titles from this"""
	dashboard = create_dashboard([
		(DashboardWidgetType.SPOTLIGHT, None, None, 6),
		(DashboardWidgetType.ROW, "Top Games", "type=game&sort=score", 8),
	])
	widgets = dashboard.widgets.all()

	rv = client.get("/api/dashboards/")
	assert rv.status_code == 200
	assert parse_json(rv.data) == [
		{
			"id": dashboard.id,
			"title": "Home",
			"widgets": [
				{"id": widgets[0].id, "type": "spotlight", "title": None, "query_string": None, "limit": 6},
				{"id": widgets[1].id, "type": "row", "title": "Top Games", "query_string": "type=game&sort=score",
					"limit": 8},
			],
		},
	]


def test_packages_sort_last_release(client):
	"""Packages are listed once each, by their newest approved release"""
	author = create_user("author")
	old = create_package("old", author)
	new = create_package("new", author)
	unapproved = create_package("unapproved", author)
	create_package("no_releases", author)

	now = datetime.datetime.now()

	def release(package, name, days_ago, approved=True):
		r = create_release(package, name, approved=approved)
		r.created_at = now - datetime.timedelta(days=days_ago)
		db.session.commit()

	# Several releases each, so that joining on releases without grouping would list them more than once
	release(old, "1.0", 10)
	release(old, "1.1", 5)
	release(new, "1.0", 8)
	release(new, "1.1", 1)
	release(unapproved, "1.0", 7)
	release(unapproved, "1.1", 0, approved=False)

	rv = client.get("/api/packages/?sort=last_release&order=desc")
	assert rv.status_code == 200
	# unapproved's newest release is unapproved, so it's ordered by its 7 day old one
	assert [package["name"] for package in parse_json(rv.data)] == ["new", "old", "unapproved"]

	rv = client.get("/api/packages/?sort=last_release&order=asc&limit=2")
	assert [package["name"] for package in parse_json(rv.data)] == ["unapproved", "old"]


def test_packages_collection(client):
	author = create_user("author")
	in_collection = create_package("in_collection", author)
	create_package("not_in_collection", author)
	create_collection(author, [in_collection], name="picks")
	create_collection(author, [in_collection], name="secret", private=True)

	rv = client.get("/api/packages/?collection=author/picks")
	assert rv.status_code == 200
	assert [package["name"] for package in parse_json(rv.data)] == ["in_collection"]

	# Collection names are per author
	assert client.get("/api/packages/?collection=someone_else/picks").status_code == 400

	# Private collections can't be listed by anyone, as API responses are cached publicly
	rv = client.get("/api/packages/?collection=author/secret")
	assert rv.status_code == 400
	assert b"Unable to find that collection" in rv.data

	for key in ["nope", "author/nope", "author/picks/extra", "/picks"]:
		assert client.get(f"/api/packages/?collection={key}").status_code == 400, key


def test_packages_collection_order(client):
	"""Collections are listed in their curated order by default"""
	author = create_user("author")
	first = create_package("first", author)
	second = create_package("second", author)
	third = create_package("third", author)
	create_package("not_in_collection", author)
	# Scores in the opposite order, so the default sort by score would list them backwards
	first.score = 1
	second.score = 2
	third.score = 3
	db.session.commit()
	create_collection(author, [first, second, third], name="picks")

	def names(url):
		rv = client.get(url)
		assert rv.status_code == 200, url
		return [package["name"] for package in parse_json(rv.data)]

	assert names("/api/packages/?collection=author/picks") == ["first", "second", "third"]
	assert names("/api/packages/?collection=author/picks&sort=collection") == ["first", "second", "third"]
	assert names("/api/packages/?collection=author/picks&order=desc") == ["third", "second", "first"]
	assert names("/api/packages/?collection=author/picks&limit=2") == ["first", "second"]

	# Another sort overrides it
	assert names("/api/packages/?collection=author/picks&sort=score") == ["third", "second", "first"]
	assert names("/api/packages/?collection=author/picks&sort=name&order=asc") == ["first", "second", "third"]

	# Without a collection, it's unchanged
	assert names("/api/packages/?sort=score")[:3] == ["third", "second", "first"]


def test_packages_sort_collection_needs_collection(client):
	rv = client.get("/api/packages/?sort=collection")
	assert rv.status_code == 400
	assert b"sort=collection needs a collection" in rv.data

