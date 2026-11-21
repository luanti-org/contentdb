# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""Setting the categories of many games at once from a CSV file, at /tags/import-categories/"""

import io

from app.models import db, AuditLogEntry, Package, PackageType, Tag, TagKind, UserRank
from ..factories import create_user, create_package, login_as, client_request


def make_category(title: str) -> Tag:
	tag = Tag(title)
	tag.kind = TagKind.CATEGORY
	tag.package_types = [PackageType.GAME]
	db.session.add(tag)
	return tag


def setup():
	# Not "Puzzle", which is a feature tag in the test data
	for title in ["Puzzle Game", "Survival Sandbox", "Adventure & RPG"]:
		make_category(title)

	author = create_user("author")
	nodecore = create_package("nodecore", author, type=PackageType.GAME)
	nodecore.title = "NodeCore"
	nodecore.tags.append(Tag.query.filter_by(name="mapgen").one())
	create_package("lott", author, type=PackageType.GAME).title = "Lord of the Test"
	for name in ["dupe_one", "dupe_two"]:
		create_package(name, create_user(f"{name}_author"), type=PackageType.GAME).title = "Same Title"
	create_package("a_mod", author).title = "A Mod"
	create_package("void", author, type=PackageType.GAME).title = "Void"
	db.session.commit()


def tag_names(name: str) -> list[str]:
	db.session.expire_all()
	return sorted(x.name for x in Package.query.filter_by(name=name).one().tags)


CSV = "\n".join([
	"Game,Main category,Second category,Link",
	"NodeCore,puzzle game,Survival Sandbox,",
	"Wrong title,Adventure & RPG,,https://content.luanti.org/packages/author/lott/",
	"Same Title,Puzzle Game,,",
	"dupe_two_author/dupe_two,Puzzle Game,,",
	"Missing Game,Puzzle Game,,",
	"A Mod,Puzzle Game,,",
	"Void,Unsure,Puzzle,",
	"",
])


def post(client, button: str, content: str = CSV):
	return client_request(client, "POST", "/tags/import-categories/", content_type="multipart/form-data", data={
		"file": (io.BytesIO(content.encode("utf-8")), "categories.csv"),
		button: "1",
	})


def test_preview_changes_nothing(client):
	setup()
	login_as(client, create_user("editor", UserRank.EDITOR))

	rv = post(client, "preview")

	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "Would change (3)" in html
	assert "Skipped (4)" in html
	assert "Several games have this title" in html
	assert "No game with this title" in html
	# Puzzle is a feature tag, not a category
	assert "Not a category: Unsure, Puzzle" in html
	assert tag_names("nodecore") == ["mapgen"]
	assert tag_names("lott") == []


def test_import_sets_categories(client):
	setup()
	login_as(client, create_user("editor", UserRank.EDITOR))

	rv = post(client, "submit")

	assert rv.status_code == 200
	assert "Changed the categories of 3 games" in rv.data.decode("utf-8")
	# Other tags are kept, and categories are matched by title or name, ignoring case
	assert tag_names("nodecore") == ["mapgen", "puzzle_game", "survival_sandbox"]
	# Found by the link, not the title
	assert tag_names("lott") == ["adventure__rpg"]
	assert tag_names("dupe_one") == []
	assert tag_names("dupe_two") == ["puzzle_game"]
	assert tag_names("a_mod") == []

	assert AuditLogEntry.query.filter(AuditLogEntry.title.like("Edited NodeCore (Category import)%")).count() == 1
	assert AuditLogEntry.query.filter_by(title="Imported categories for 3 games from a CSV file").count() == 1

	# Running it again changes nothing
	rv = post(client, "submit")
	html = rv.data.decode("utf-8")
	assert "Changed (0)" in html
	assert "Already correct (3)" in html


def test_import_replaces_categories(client):
	setup()
	package = Package.query.filter_by(name="nodecore").one()
	package.tags.append(Tag.query.filter_by(name="adventure__rpg").one())
	db.session.commit()
	login_as(client, create_user("editor", UserRank.EDITOR))

	post(client, "submit", "Game,Main category\nNodeCore,Puzzle Game\n")

	assert tag_names("nodecore") == ["mapgen", "puzzle_game"]


def test_import_reports_bad_file(client):
	setup()
	login_as(client, create_user("editor", UserRank.EDITOR))

	rv = post(client, "submit", "Title,Category\nNodeCore,Puzzle\n")

	assert rv.status_code == 200
	assert "Missing columns: game, main category" in rv.data.decode("utf-8")
	assert tag_names("nodecore") == ["mapgen"]


def test_import_needs_permission(client):
	setup()
	login_as(client, create_user("member"))

	assert client_request(client, "GET", "/tags/import-categories/").status_code == 403
	assert post(client, "submit").status_code == 403
	assert tag_names("nodecore") == ["mapgen"]
