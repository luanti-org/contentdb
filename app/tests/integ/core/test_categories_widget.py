# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""The categories widget: a tile for each category tag that has packages"""

from app.models import db, DashboardWidgetType, PackageState, PackageType, Tag, TagKind
from ..factories import create_dashboard, create_package, create_user


def make_category(title: str, description: str | None = None) -> Tag:
	tag = Tag(title)
	tag.kind = TagKind.CATEGORY
	tag.package_types = [PackageType.GAME]
	tag.description = description
	db.session.add(tag)
	db.session.commit()
	return tag


def test_category_tiles(client):
	author = create_user("author")
	# Created out of alphabetical order, as tiles are in creation order
	survival = make_category("Survival Sandbox", "Gather & survive")
	puzzle = make_category("Puzzle Game")
	puzzle.icon = "fa-puzzle-piece"
	racing = make_category("Racing")
	make_category("Strategy")
	mapgen = Tag.query.filter_by(name="mapgen").one()

	games = [create_package(f"game{i}", author, type=PackageType.GAME) for i in range(3)]
	for game in games:
		game.tags.extend([survival, mapgen])
	games[0].tags.append(puzzle)
	# Only a work in progress game has this category
	wip_game = create_package("wip_game", author, state=PackageState.WIP, type=PackageType.GAME)
	wip_game.tags.append(racing)
	db.session.commit()

	create_dashboard([(DashboardWidgetType.CATEGORIES, "Browse by category", "type=game", None)])
	html = client.get("/").data.decode("utf-8")

	assert "Browse by category" in html
	assert html.count('class="packagetile category-tile"') == 2, "categories without published packages, and feature tags, aren't shown"
	assert html.index(">Survival Sandbox<") < html.index(">Puzzle Game<")
	assert ">Racing<" not in html
	assert ">Mapgen<" not in html

	# The title, with the description in the drop down shown on hover, like a package tile
	tile = html[html.index('href="/packages/?type=game&amp;tag=survival_sandbox"'):]
	tile = tile[:tile.index("</a>")]
	assert '<i class="fas fa-gamepad category-icon" aria-hidden="true"></i>' in tile, "the default icon"
	assert '<div class="info-wrapper">' in tile
	assert "<p>Gather &amp; survive</p>" in tile

	# No drop down without a description
	tile = html[html.index('href="/packages/?type=game&amp;tag=puzzle_game"'):]
	tile = tile[:tile.index("</a>")]
	assert "info-wrapper" not in tile
	# The icon chosen in the tag editor
	assert '<i class="fas fa-puzzle-piece category-icon" aria-hidden="true"></i>' in tile


def test_category_tiles_use_base_query(client):
	author = create_user("author")
	puzzle = make_category("Puzzle Game")
	game = create_package("game", author, type=PackageType.GAME)
	game.tags.append(puzzle)
	db.session.commit()

	create_dashboard([(DashboardWidgetType.CATEGORIES, "Browse by category", "author=someone_else", None)])
	html = client.get("/").data.decode("utf-8")

	# No tiles, so nothing at all, not even the title
	assert "Browse by category" not in html
	assert "category-tile" not in html
