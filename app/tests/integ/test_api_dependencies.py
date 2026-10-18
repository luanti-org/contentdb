# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from app.default_data import populate_test_data
from app.models import db, Package, PackageState, Dependency, MetaPackage
from .utils import parse_json, count_queries
from .utils import client # noqa


def test_all_dependencies(client):
	populate_test_data(db.session)
	food_sweet = Package.query.filter_by(name="food_sweet").one()
	food = Package.query.filter_by(name="food").one()
	db.session.add(Dependency(food_sweet, meta=MetaPackage("sfinv"), optional=True))
	db.session.add(Dependency(food_sweet, package=food, optional=True))
	db.session.commit()

	approved = Package.query.filter_by(state=PackageState.APPROVED).all()
	data = parse_json(client.get("/api/dependencies/?n=300").data)
	assert data["total"] == len(approved)
	items = {(x["author"], x["name"]): x for x in data["items"]}
	assert len(items) == len(approved)

	for package in approved:
		item = items[(package.author.username, package.name)]
		assert item["type"] == package.type.to_name()
		assert item["provides"] == [x.name for x in package.provides]
		assert sorted(item["depends"]) == sorted(str(x) for x in package.dependencies if not x.optional)
		assert sorted(item["optional_depends"]) == sorted(str(x) for x in package.dependencies if x.optional)

	assert items[("rubenwardy", "food_sweet")]["depends"] == ["food"]
	assert sorted(items[("rubenwardy", "food_sweet")]["optional_depends"]) == ["rubenwardy/food", "sfinv"]


def test_all_dependencies_query_count_is_constant(client):
	populate_test_data(db.session)
	db.session.commit()
	client.get("/api/dependencies/?n=1")

	one = count_queries(lambda: client.get("/api/dependencies/?n=1"))
	all_ = count_queries(lambda: client.get("/api/dependencies/?n=300"))
	assert all_ == one


def test_all_dependencies_pages_cover_every_package_once(client):
	populate_test_data(db.session)
	db.session.commit()

	keys: list[tuple[str, str]] = []
	page = 1
	while True:
		data = parse_json(client.get(f"/api/dependencies/?n=2&page={page}").data)
		keys.extend((x["author"], x["name"]) for x in data["items"])
		if page >= data["page_count"]:
			break
		page += 1

	assert len(keys) == len(set(keys)) == Package.query.filter_by(state=PackageState.APPROVED).count()
