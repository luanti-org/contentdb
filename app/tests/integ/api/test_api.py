# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

from app.default_data import populate_test_data
from app.models import db, Package, PackageState, DashboardWidgetType
from ..factories import create_dashboard, create_package, create_release, create_user
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
