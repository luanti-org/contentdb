# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
import json
import os
import zipfile

import pytest

from app.default_data import populate_test_data
from app.models import db, User, UserRank, Dependency, MetaPackage, ContentWarning, Language, PackageAlias, \
	PackageTranslation, PackageGameSupport, PackageType, PackageState, PackageRelease, ReleaseState, PackageScreenshot, Package
from app.tasks.dumptask import create_database_dump
from app.uploads import copy_to_uploads, local
from ..utils import make_package


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
	monkeypatch.setattr(local, "upload_dir", str(tmp_path))
	return tmp_path


def test_database_dump_uses_documented_name(client, upload_dir):
	populate_test_data(db.session)
	db.session.commit()

	create_database_dump()

	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	assert os.listdir(upload_dir) == [f"backup-{date}.zip"]

	with zipfile.ZipFile(upload_dir / f"backup-{date}.zip") as zipf:
		index = json.loads(zipf.read("backup/index.json"))
		assert index["version"] == 1
		assert "created_at" in index
		assert any(name.endswith("/mesecons/index.json") for name in zipf.namelist())


def test_database_dump_replaces_same_day(client, upload_dir):
	create_database_dump()
	create_database_dump()
	assert len(os.listdir(upload_dir)) == 1


def test_copy_to_uploads_random_name_by_default(client, upload_dir, tmp_path_factory):
	src = tmp_path_factory.mktemp("src") / "backup-2026-11-04.zip"
	src.write_bytes(b"data")

	upload_path = copy_to_uploads(str(src))
	assert upload_path != "/uploads/backup-2026-11-04.zip"
	assert upload_path.endswith(".zip")
	assert (upload_dir / os.path.basename(upload_path)).read_bytes() == b"data"


@pytest.mark.parametrize("filename", [
	"", ".zip", ".hidden", "../backup.zip", "a/b.zip", "a\\b.zip", "backup..zip", "backup.zip.", "back up.zip",
])
def test_copy_to_uploads_rejects_unsafe_names(client, upload_dir, tmp_path_factory, filename):
	src = tmp_path_factory.mktemp("src") / "file.zip"
	src.write_bytes(b"data")

	with pytest.raises(ValueError):
		copy_to_uploads(str(src), filename)
	assert os.listdir(upload_dir) == []


def read_package_index(upload_dir, author: str, name: str) -> dict:
	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	with zipfile.ZipFile(upload_dir / f"backup-{date}.zip") as zipf:
		return json.loads(zipf.read(f"backup/{author}/{name}/index.json"))


def test_database_dump_includes_dependencies(client, upload_dir):
	author = User.query.filter_by(username="rubenwardy").one()
	library = make_package("library_pkg", author)
	package = make_package("depender_pkg", author)
	make_package("no_deps_pkg", author)

	package.provides.append(MetaPackage("depender_api"))
	db.session.add(Dependency(package, meta=MetaPackage("default"), optional=False))
	db.session.add(Dependency(package, package=library, optional=False))
	db.session.add(Dependency(package, meta=MetaPackage("mesecons"), optional=True))
	db.session.add(Dependency(package, meta=MetaPackage("awards"), optional=True))
	db.session.commit()

	create_database_dump()

	data = read_package_index(upload_dir, "rubenwardy", "depender_pkg")
	assert data["provides"] == ["depender_api"]
	assert data["depends"] == ["default", "library_pkg"]
	assert data["optional_depends"] == ["awards", "mesecons"]

	data = read_package_index(upload_dir, "rubenwardy", "no_deps_pkg")
	assert data["provides"] == []
	assert data["depends"] == []
	assert data["optional_depends"] == []


def read_dump_file(upload_dir, path: str):
	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	with zipfile.ZipFile(upload_dir / f"backup-{date}.zip") as zipf:
		return json.loads(zipf.read(f"backup/{path}"))


def add_language(id: str, title: str):
	language = Language()
	language.id = id
	language.title = title
	db.session.add(language)


def add_game_support(package: Package, game: Package):
	support = PackageGameSupport()
	support.package = package
	support.game = game
	support.supports = True
	support.confidence = 8
	db.session.add(support)


def test_database_dump_lookup_tables(client, upload_dir):
	db.session.add(ContentWarning("Gore", "Contains blood"))
	add_language("fr", "Français")
	db.session.commit()

	create_database_dump()

	licenses = {x["name"]: x for x in read_dump_file(upload_dir, "licenses.json")}
	assert licenses["MIT"]["is_foss"] is True
	assert licenses["CC-BY-NC-SA"]["is_foss"] is False

	tags = {x["name"]: x for x in read_dump_file(upload_dir, "tags.json")}
	assert tags["mapgen"]["title"] == "Mapgen"
	assert len(tags["mapgen"]["background_color"]) == 6

	assert read_dump_file(upload_dir, "content_warnings.json") == [
		{"name": "gore", "title": "Gore", "description": "Contains blood"}]
	assert {"id": "fr", "title": "Français"} in read_dump_file(upload_dir, "languages.json")


def test_database_dump_package_details(client, upload_dir):
	author = User.query.filter_by(username="rubenwardy").one()
	maintainer = User("maintainer_only", active=True)
	maintainer.rank = UserRank.MEMBER
	db.session.add(maintainer)

	package = make_package("detailed_pkg", author)
	package.maintainers.append(maintainer)
	package.aliases.append(PackageAlias("old_author", "old_name"))

	add_language("fr", "Français")
	translation = PackageTranslation()
	translation.package = package
	translation.language_id = "fr"
	translation.title = "Paquet"
	translation.short_desc = "Court"
	translation.desc = "Long"
	db.session.add(translation)

	approved_game = make_package("approved_game", author)
	approved_game.type = PackageType.GAME
	draft_game = make_package("draft_game", author)
	draft_game.type = PackageType.GAME
	draft_game.state = PackageState.WIP
	add_game_support(package, approved_game)
	add_game_support(package, draft_game)

	for name, state in [("v1", ReleaseState.APPROVED), ("v2", ReleaseState.FAILED), ("v3", ReleaseState.PROCESSING)]:
		release = PackageRelease()
		release.package = package
		release.name = name
		release.title = name
		release.state = state
		release.upload_path = f"/uploads/{name}.zip"
		db.session.add(release)

	screenshots = []
	for order, (title, approved) in enumerate([("First", True), ("Hidden", False), ("Cover", True)]):
		ss = PackageScreenshot()
		ss.package = package
		ss.title = title
		ss.order = order
		ss.upload_path = f"/uploads/{title.lower()}.png"
		ss.width = 1280
		ss.height = 720
		ss.approved = approved
		db.session.add(ss)
		screenshots.append(ss)
	db.session.flush()
	package.cover_image = screenshots[2]
	db.session.commit()

	create_database_dump()

	# Maintainers who don't author an approved package are included
	assert read_dump_file(upload_dir, "maintainer_only/index.json")["username"] == "maintainer_only"

	data = read_dump_file(upload_dir, "rubenwardy/detailed_pkg/index.json")
	assert data["maintainers"] == ["maintainer_only"]
	assert data["aliases"] == [{"author": "old_author", "name": "old_name"}]
	assert data["translations"] == {"fr": {"title": "Paquet", "short_desc": "Court", "desc": "Long"}}
	assert [x["game"]["name"] for x in data["game_support"]] == ["approved_game"]
	assert len(data["screenshots"]) == 2
	assert not any("hidden" in url for url in data["screenshots"])

	releases = read_dump_file(upload_dir, "rubenwardy/detailed_pkg/releases.json")
	assert [x["name"] for x in releases] == ["v1"]

	screenshot_data = read_dump_file(upload_dir, "rubenwardy/detailed_pkg/screenshots.json")
	assert [x["title"] for x in screenshot_data] == ["First", "Cover"]
	assert screenshot_data[0]["filename"] == "first.png"
	assert screenshot_data[0]["width"] == 1280 and screenshot_data[0]["height"] == 720
	assert [x["is_cover_image"] for x in screenshot_data] == [False, True]

	# Drafts aren't included at all
	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	with zipfile.ZipFile(upload_dir / f"backup-{date}.zip") as zipf:
		assert not any("draft_game" in name for name in zipf.namelist())
