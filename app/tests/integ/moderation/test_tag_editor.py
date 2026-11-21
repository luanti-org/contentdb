# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""Tag kinds and the package types a tag can be given to"""

import re

from app.models import db, PackageType, Tag, TagKind, UserRank
from ..factories import create_user, login_as


def get_tag(name: str) -> Tag:
	db.session.expire_all()
	return Tag.query.filter_by(name=name).one()


def make_tag(title: str, kind: TagKind = TagKind.FEATURE, package_types: list[PackageType] | None = None) -> Tag:
	tag = Tag(title)
	tag.kind = kind
	tag.package_types = package_types or []
	db.session.add(tag)
	db.session.commit()
	return tag


def test_new_tags_default_to_feature_for_all_types(client):
	tag = make_tag("Shiny")
	saved = get_tag(tag.name)
	assert saved.kind == TagKind.FEATURE
	assert saved.package_types == []


def test_create_category_tag(client):
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	rv = client.post("/tags/new/", data={
		"title": "Survival Sandbox",
		"description": "Survive and build",
		"kind": "CATEGORY",
		"package_types": ["game"],
	})
	assert rv.status_code == 302

	tag = get_tag("survival_sandbox")
	assert tag.kind == TagKind.CATEGORY
	assert tag.package_types == [PackageType.GAME]

	html = client.get("/tags/").data.decode("utf-8")
	assert "Category: Game" in html


def test_edit_tag_kind_and_types(client):
	make_tag("Puzzle Game")
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	rv = client.post("/tags/puzzle_game/edit/", data={
		"title": "Puzzle Game",
		"name": "puzzle_game",
		"kind": "CATEGORY",
		"package_types": ["game", "mod"],
	})
	assert rv.status_code == 302
	tag = get_tag("puzzle_game")
	assert tag.kind == TagKind.CATEGORY
	assert sorted(x.name for x in tag.package_types) == ["GAME", "MOD"]

	# Shown ticked in the editor
	html = client.get("/tags/puzzle_game/edit/").data.decode("utf-8")
	checked = [x for x in re.findall(r"<input[^>]*>", html) if " checked" in x]
	assert any('name="kind"' in x and 'value="CATEGORY"' in x for x in checked)
	assert sorted(re.findall(r'value="(\w+)"', x)[0] for x in checked if 'name="package_types"' in x) == ["game", "mod"]

	# Unticking every type means all types
	rv = client.post("/tags/puzzle_game/edit/", data={
		"title": "Puzzle Game",
		"name": "puzzle_game",
		"kind": "FEATURE",
	})
	assert rv.status_code == 302
	tag = get_tag("puzzle_game")
	assert tag.kind == TagKind.FEATURE
	assert tag.package_types == []


def test_edit_tag_rejects_unknown_kind_and_type(client):
	make_tag("Puzzle Game")
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	invalid: list[dict[str, str | list[str]]] = [{"kind": "NOPE"}, {"kind": "CATEGORY", "package_types": ["nope"]}]
	for data in invalid:
		rv = client.post("/tags/puzzle_game/edit/", data={"title": "Puzzle Game", "name": "puzzle_game", **data})
		assert rv.status_code == 200
		assert get_tag("puzzle_game").kind == TagKind.FEATURE


def test_applies_to_filter(client):
	make_tag("Everything")
	make_tag("Game Only", TagKind.CATEGORY, [PackageType.GAME])
	make_tag("Mods and Packs", package_types=[PackageType.MOD, PackageType.TXP])

	def names(package_type: PackageType) -> list[str]:
		query = Tag.query.filter(Tag.name.in_(["everything", "game_only", "mods_and_packs"]))
		return sorted(x.name for x in query.filter(Tag.applies_to_filter(package_type)).all())

	assert names(PackageType.GAME) == ["everything", "game_only"]
	assert names(PackageType.MOD) == ["everything", "mods_and_packs"]
	assert names(PackageType.TXP) == ["everything", "mods_and_packs"]
