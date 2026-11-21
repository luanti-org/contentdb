# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""Server-rendered pictures of each category's top packages, for the homepage's category tiles"""

import os

import pytest
from PIL import Image

from app.blueprints.homepage.widgets.categories import get_hues
from app.models import db, DashboardWidgetType, Package, PackageState, PackageType, Tag, TagKind, User
from app.tasks.collagetasks import update_category_collages
from app.uploads import local
from app.utils.collage import OUTPUT_SIZE
from ..factories import create_dashboard, create_package, create_screenshot, create_user


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
	monkeypatch.setattr(local, "upload_dir", str(tmp_path))
	return tmp_path


def make_category(title: str) -> Tag:
	tag = Tag(title)
	tag.kind = TagKind.CATEGORY
	tag.package_types = [PackageType.GAME]
	db.session.add(tag)
	db.session.commit()
	return tag


def make_game(name: str, author: User, tag: Tag, upload_dir, colour: tuple[int, int, int],
		state: PackageState = PackageState.APPROVED) -> Package:
	game = create_package(name, author, state=state, type=PackageType.GAME)
	game.tags.append(tag)
	screenshot = create_screenshot(game)
	Image.new("RGB", (1280, 720), colour).save(upload_dir / os.path.basename(screenshot.upload_path))
	db.session.commit()
	return game


def get_tag(name: str) -> Tag:
	db.session.expire_all()
	return Tag.query.filter_by(name=name).one()


def test_collages_are_rendered_and_replaced(client, upload_dir):
	author = create_user("author")
	puzzle = make_category("Puzzle Game")
	make_category("Racing")
	make_game("one", author, puzzle, upload_dir, (200, 0, 0))
	make_game("two", author, puzzle, upload_dir, (0, 200, 0))

	update_category_collages()

	path = get_tag("puzzle_game").collage_path
	assert path is not None and os.path.basename(path).startswith("category-puzzle_game-")
	with Image.open(upload_dir / os.path.basename(path)) as image:
		assert image.format == "WEBP"
		assert image.size == OUTPUT_SIZE
	# A category without packages gets no picture
	assert get_tag("racing").collage_path is None

	# Unchanged packages keep the same file
	update_category_collages()
	assert get_tag("puzzle_game").collage_path == path

	# A new top package changes the picture, and the old file is deleted
	make_game("three", author, get_tag("puzzle_game"), upload_dir, (0, 0, 200))
	update_category_collages()
	new_path = get_tag("puzzle_game").collage_path
	assert new_path != path
	assert (upload_dir / os.path.basename(new_path)).is_file()
	assert not (upload_dir / os.path.basename(path)).exists()


def test_collages_ignore_unapproved_packages(client, upload_dir):
	author = create_user("author")
	puzzle = make_category("Puzzle Game")
	make_game("wip", author, puzzle, upload_dir, (200, 0, 0), state=PackageState.WIP)

	update_category_collages()

	assert get_tag("puzzle_game").collage_path is None


def test_category_tile_shows_collage(client, upload_dir):
	author = create_user("author")
	puzzle = make_category("Puzzle Game")
	racing = make_category("Racing")
	make_game("one", author, puzzle, upload_dir, (200, 0, 0))
	# Packages without screenshots still count for the tile, but there's no picture
	game = create_package("two", author, type=PackageType.GAME)
	game.tags.append(racing)
	db.session.commit()
	update_category_collages()

	create_dashboard([(DashboardWidgetType.CATEGORIES, "Categories", "type=game", None)])
	html = client.get("/").data.decode("utf-8")

	path = get_tag("puzzle_game").collage_path
	puzzle_tile = html[html.index('tag=puzzle_game"'):]
	puzzle_tile = puzzle_tile[:puzzle_tile.index("</a>")]
	assert f'<img class="category-image" src="{path}"' in puzzle_tile

	racing_start = html.rindex("<a ", 0, html.index('tag=racing"'))
	racing_tile = html[racing_start:]
	racing_tile = racing_tile[:racing_tile.index("</a>")]
	# Each category has its own hue, by its order among all categories
	assert f"--tile-hue: {get_hues(2)[1]};" in racing_tile
	assert f"--tile-hue: {get_hues(2)[0]};" in puzzle_tile
	assert "category-image" not in racing_tile
	# Only the tag's collage is loaded, not its packages' thumbnails
	assert "/thumbnails/" not in html[html.index('class="category-grid'):]
