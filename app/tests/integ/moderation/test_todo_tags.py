# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""/todo/tags/, the list of packages and their tags"""

from contextlib import contextmanager

from sqlalchemy import event

from app.blueprints.todo import editor
from app.models import db, PackageType, Tag, TagKind, UserRank
from ..factories import create_package, create_user, login_as, client_request


@contextmanager
def count_queries():
	queries: list[str] = []

	def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
		queries.append(statement)

	event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
	try:
		yield queries
	finally:
		event.remove(db.engine, "before_cursor_execute", before_cursor_execute)


def make_packages(start: int, count: int):
	author = create_user(f"author{start}")
	maintainer = create_user(f"maintainer{start}")
	mapgen = Tag.query.filter_by(name="mapgen").one()
	for i in range(start, start + count):
		package = create_package(f"pkg{i}", author, maintainers=[maintainer])
		package.tags.append(mapgen)
	db.session.commit()


def get_query_count(client) -> int:
	db.session.expire_all()
	with count_queries() as queries:
		rv = client_request(client, "GET", "/todo/tags/")
		assert rv.status_code == 200
	return len(queries)


def test_queries_dont_grow_with_packages(client):
	"""Each row's tags, author, and maintainers (for the edit links) are loaded with the page, not one row at a time"""
	login_as(client, create_user("curator", UserRank.CURATOR))
	make_packages(0, 2)
	few = get_query_count(client)

	make_packages(2, 10)
	many = get_query_count(client)

	assert many == few


def test_pagination(client, monkeypatch):
	monkeypatch.setattr(editor, "TAGS_PAGE_SIZE", 2)
	login_as(client, create_user("curator", UserRank.CURATOR))
	make_packages(0, 3)

	first = client_request(client, "GET", "/todo/tags/?sort=name&order=asc").data.decode("utf-8")
	assert "pkg0" in first and "pkg1" in first and "pkg2" not in first
	assert "page=2" in first

	second = client_request(client, "GET", "/todo/tags/?sort=name&order=asc&page=2").data.decode("utf-8")
	assert "pkg2" in second and "pkg0" not in second

	# Tag badges filter the list, from its first page
	assert "tag=mapgen" in second
	badge = second[second.index("tag=mapgen") - 200:second.index("tag=mapgen")]
	assert "page=1" in badge


def test_missing_tags_only(client):
	login_as(client, create_user("curator", UserRank.CURATOR))
	make_packages(0, 1)
	create_package("untagged", create_user("other"))

	html = client_request(client, "GET", "/todo/tags/?no_tags=1").data.decode("utf-8")

	assert "untagged" in html
	assert "pkg0" not in html


def make_category_only_game() -> Tag:
	category = Tag("Some Category")
	category.kind = TagKind.CATEGORY
	category.package_types = [PackageType.GAME]
	game = create_package("category_only", create_user("gamedev"), type=PackageType.GAME)
	game.tags.append(category)
	db.session.commit()
	return category


def test_missing_tags_only_counts_category_as_missing(client):
	"""A game with a category but no feature tags still needs tagging"""
	login_as(client, create_user("curator", UserRank.CURATOR))
	make_packages(0, 1)
	make_category_only_game()

	html = client_request(client, "GET", "/todo/tags/?no_tags=1").data.decode("utf-8")

	assert "category_only" in html
	assert "pkg0" not in html


def test_editor_todo_counts_category_as_missing(client):
	login_as(client, create_user("editor", UserRank.EDITOR))
	make_packages(0, 1)
	make_category_only_game()

	html = client_request(client, "GET", "/todo/").data.decode("utf-8")

	assert "1 / 2 packages don't have any tags." in html


def test_categories_shown_first(client):
	login_as(client, create_user("curator", UserRank.CURATOR))
	category = make_category_only_game()
	game = db.session.merge(category).packages[0]
	game.tags.append(Tag.query.filter_by(name="mapgen").one())
	db.session.commit()

	html = client_request(client, "GET", "/todo/tags/?type=game").data.decode("utf-8")

	category_badge = html.index(f"tag={category.name}&amp;")
	feature_badge = html.index("tag=mapgen&amp;")
	assert category_badge < feature_badge
	assert "badge bg-primary" in html[category_badge - 100:category_badge]
	assert "badge bg-secondary" in html[feature_badge - 100:feature_badge]
