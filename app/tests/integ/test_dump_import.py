# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
import importlib.util
import json
import os
import zipfile
from pathlib import Path

import pytest

from app.default_data import populate_test_data
from app.domain.dump_import import import_dump, DumpImportError
from app.models import db, User, UserRank, Package, PackageType, PackageState, PackageDevState, License, Tag, \
	ContentWarning, Language, MetaPackage, Dependency, PackageTranslation, PackageAlias, PackageRelease, \
	ReleaseState, PackageScreenshot, PackageGameSupport, LuantiRelease
from app.tasks.dumptask import create_database_dump
from app.tasks.usertasks import delete_inactive_users
from app.uploads import local
from .utils import make_package, recreate_db
from .utils import client # noqa


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
	monkeypatch.setattr(local, "upload_dir", str(tmp_path))
	return tmp_path


def make_dump(upload_dir: Path) -> str:
	create_database_dump()
	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	return str(upload_dir / f"backup-{date}.zip")


def add_user(username: str, rank: UserRank, github: str | None = None, forums: str | None = None) -> User:
	user = User(username, active=True)
	user.rank = rank
	user.github_username = github
	user.forums_username = forums
	db.session.add(user)
	return user


def setup_source_data():
	"""Creates packages covering everything in the dump. Returns the editor user"""
	admin = User.query.filter_by(username="rubenwardy").one()

	editor = add_user("editor_user", UserRank.EDITOR, github="EditorGH", forums="editor_forum")
	editor.display_name = "Editor Person"
	editor.website_url = "https://editor.example.com"
	editor.donate_url = "https://donate.example.com/editor"
	maintainer = add_user("maintainer_only", UserRank.MEMBER)

	game = make_package("imported_game", admin)
	game.type = PackageType.GAME

	package = make_package("imported_mod", editor)
	package.title = "Imported Mod"
	package.dev_state = PackageDevState.BETA
	package.created_at = datetime.datetime(2020, 1, 2, 3, 4, 5)
	package.approved_at = datetime.datetime(2020, 1, 3, 3, 4, 5)
	package.repo = "https://github.com/example/imported_mod"
	package.forums = 1234
	package.downloads = 50
	package.score = 100.5
	package.score_downloads = 80.25
	package.maintainers.append(editor)
	package.maintainers.append(maintainer)
	package.tags.append(Tag.query.filter_by(name="mapgen").one())

	warning = ContentWarning("Gore", "Contains blood")
	db.session.add(warning)
	package.content_warnings.append(warning)

	package.provides.append(MetaPackage("imported_api"))
	db.session.add(Dependency(package, meta=MetaPackage("default"), optional=False))
	db.session.add(Dependency(package, meta=MetaPackage("awards"), optional=True))
	package.aliases.append(PackageAlias("old_author", "old_name"))

	language = Language()
	language.id = "fr"
	language.title = "Français"
	db.session.add(language)

	translation = PackageTranslation()
	translation.package = package
	translation.language_id = "fr"
	translation.title = "Mod importé"
	translation.short_desc = "Court"
	translation.desc = "Long"
	db.session.add(translation)

	support = PackageGameSupport()
	support.package = package
	support.game = game
	support.supports = True
	support.confidence = 8
	db.session.add(support)

	new_luanti = LuantiRelease("5.99", 99)
	db.session.add(new_luanti)
	release = PackageRelease()
	release.package = package
	release.name = "v1.0.0"
	release.title = "Version 1"
	release.release_notes = "Notes"
	release.upload_path = "/uploads/abcdef1234.zip"
	release.state = ReleaseState.APPROVED
	release.commit_hash = "a" * 40
	release.downloads = 7
	release.file_size_bytes = 1024
	release.file_sha256 = "b" * 64
	release.min_rel = new_luanti
	db.session.add(release)

	screenshots = []
	for order, title in enumerate(["First", "Cover"]):
		ss = PackageScreenshot()
		ss.package = package
		ss.title = title
		ss.order = order
		ss.upload_path = f"/uploads/{title.lower()}1234.png"
		ss.width = 1280
		ss.height = 720
		ss.file_size_bytes = 2048
		ss.approved = True
		db.session.add(ss)
		screenshots.append(ss)
	db.session.flush()
	package.cover_image = screenshots[1]

	db.session.commit()
	return editor


def test_round_trip_into_fresh_database(client, upload_dir):
	setup_source_data()
	path = make_dump(upload_dir)

	recreate_db()
	assert Package.query.filter_by(name="imported_mod").count() == 0

	summary = import_dump(path)
	db.session.commit()
	assert summary.packages_created == 2
	assert summary.packages_existing == []
	assert summary.users_created == 2
	assert summary.users_existing == 1
	assert summary.warnings == []

	# Ranks from the dump are ignored, and existing users are left unchanged
	editor = User.query.filter_by(username="editor_user").one()
	assert editor.rank == UserRank.NOT_JOINED
	assert not editor.is_active
	assert editor.display_name == "Editor Person"
	assert editor.website_url == "https://editor.example.com"
	assert editor.github_username == "EditorGH"
	assert editor.forums_username == "editor_forum"
	assert editor.email is None and editor.password is None
	assert User.query.filter_by(username="maintainer_only").one().rank == UserRank.NOT_JOINED
	assert User.query.filter_by(username="rubenwardy").one().rank == UserRank.ADMIN

	package = Package.query.filter_by(name="imported_mod").one()
	assert package.author == editor
	assert package.title == "Imported Mod"
	assert package.state == PackageState.APPROVED
	assert package.dev_state == PackageDevState.BETA
	assert package.created_at == datetime.datetime(2020, 1, 2, 3, 4, 5)
	assert package.approved_at == datetime.datetime(2020, 1, 3, 3, 4, 5)
	assert package.license.name == "MIT"
	assert package.repo == "https://github.com/example/imported_mod"
	assert package.forums == 1234
	assert package.downloads == 50
	assert package.score == 100.5
	assert package.score_downloads == 80.25
	# Falls back to the author's donate URL, rather than being copied onto the package
	assert package.donate_url is None
	assert package.donate_url_actual == "https://donate.example.com/editor"

	assert {x.username for x in package.maintainers} == {"editor_user", "maintainer_only"}
	assert [x.name for x in package.tags] == ["mapgen"]
	assert [x.name for x in package.content_warnings] == ["gore"]
	assert ContentWarning.query.filter_by(name="gore").one().description == "Contains blood"
	assert [x.name for x in package.provides] == ["imported_api"]
	assert sorted((x.get_name(), x.optional) for x in package.dependencies) == [("awards", True), ("default", False)]
	assert [(x.author, x.name) for x in package.aliases] == [("old_author", "old_name")]

	translation = package.translations.filter_by(language_id="fr").one()
	assert (translation.title, translation.short_desc, translation.desc) == ("Mod importé", "Court", "Long")

	support = package.supported_games.one()
	assert support.game.name == "imported_game"
	assert support.game.author.username == "rubenwardy"
	assert (support.supports, support.confidence) == (True, 8)

	release = package.releases.one()
	assert release.name == "v1.0.0"
	assert release.title == "Version 1"
	assert release.release_notes == "Notes"
	assert release.state == ReleaseState.APPROVED
	assert release.upload_path == "/uploads/abcdef1234.zip"
	assert release.commit_hash == "a" * 40
	assert release.downloads == 7
	assert release.file_size_bytes == 1024
	assert release.file_sha256 == "b" * 64
	assert release.min_rel.name == "5.99" and release.min_rel.protocol == 99
	assert release.max_rel is None

	screenshots = package.screenshots.all()
	assert [(x.title, x.order, x.upload_path) for x in screenshots] == [
		("First", 0, "/uploads/first1234.png"), ("Cover", 1, "/uploads/cover1234.png")]
	assert all(x.approved and x.width == 1280 and x.height == 720 and x.file_size_bytes == 2048 for x in screenshots)
	assert package.cover_image == screenshots[1]

	# The package page renders
	rv = client.get("/packages/editor_user/imported_mod/")
	assert rv.status_code == 200
	assert b"Imported Mod" in rv.data


def test_import_into_same_database_skips_everything(client, upload_dir):
	populate_test_data(db.session)
	db.session.commit()
	path = make_dump(upload_dir)

	packages_before = Package.query.count()
	users_before = User.query.count()

	summary = import_dump(path)
	db.session.commit()

	assert summary.packages_created == 0
	assert summary.users_created == 0
	assert len(summary.packages_existing) == Package.query.filter_by(state=PackageState.APPROVED).count()
	assert Package.query.count() == packages_before
	assert User.query.count() == users_before


def test_conflicting_usernames_are_left_empty(client, upload_dir):
	setup_source_data()
	path = make_dump(upload_dir)

	recreate_db()
	add_user("someone_else", UserRank.MEMBER, github="editorgh", forums="EDITOR_FORUM")
	db.session.commit()

	summary = import_dump(path)
	db.session.commit()

	editor = User.query.filter_by(username="editor_user").one()
	assert editor.github_username is None
	assert editor.forums_username is None
	assert len(summary.warnings) == 2
	assert all(x.startswith("editor_user: ") for x in summary.warnings)
	assert User.query.filter_by(username="someone_else").one().github_username == "editorgh"


def test_maintainer_only_user_is_not_deleted_as_inactive(client, upload_dir):
	setup_source_data()
	path = make_dump(upload_dir)

	recreate_db()
	import_dump(path)
	db.session.commit()

	maintainer = User.query.filter_by(username="maintainer_only").one()
	maintainer.created_at = datetime.datetime.now() - datetime.timedelta(days=1)
	db.session.commit()

	delete_inactive_users()
	assert User.query.filter_by(username="maintainer_only").count() == 1


def write_zip(path: Path, files: dict[str, str]) -> str:
	with zipfile.ZipFile(path, "w") as zipf:
		for name, content in files.items():
			zipf.writestr(name, content)
	return str(path)


@pytest.mark.parametrize("files", [
	{"backup/index.json": json.dumps({"version": 2, "created_at": "2026-11-04T00:00:00"})},
	{"backup/index.json": json.dumps({"created_at": "2026-11-04T00:00:00"})},
	{"backup/other.json": "{}"},
	{"backup/index.json": "not json"},
])
def test_invalid_dumps_are_rejected(client, tmp_path, files):
	path = write_zip(tmp_path / "dump.zip", files)
	with pytest.raises(DumpImportError):
		import_dump(path)


def test_non_zip_is_rejected(client, tmp_path):
	path = tmp_path / "dump.zip"
	path.write_text("not a zip")
	with pytest.raises(DumpImportError):
		import_dump(str(path))


def test_failed_import_changes_nothing(client, upload_dir, tmp_path):
	setup_source_data()
	path = make_dump(upload_dir)
	recreate_db()
	licenses_before = License.query.count()

	# Remove a license that a package uses, so the import fails partway through
	with zipfile.ZipFile(path) as src:
		files = {name: src.read(name).decode() for name in src.namelist()}
	licenses = [x for x in json.loads(files["backup/licenses.json"]) if x["name"] != "MIT"]
	files["backup/licenses.json"] = json.dumps(licenses)
	db.session.delete(License.query.filter_by(name="MIT").one())
	db.session.commit()

	with pytest.raises(DumpImportError, match="unknown license MIT"):
		import_dump(write_zip(tmp_path / "broken.zip", files))
	db.session.rollback()

	assert User.query.filter_by(username="editor_user").count() == 0
	assert Package.query.filter_by(name="imported_mod").count() == 0
	assert License.query.count() == licenses_before - 1


def load_import_script():
	script = Path(__file__).parents[3] / "utils" / "import_dump.py"
	spec = importlib.util.spec_from_file_location("import_dump_script", script)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def test_script_dry_run_and_import(client, upload_dir, capsys):
	setup_source_data()
	path = make_dump(upload_dir)
	recreate_db()

	script = load_import_script()
	assert script.main([path, "--dry-run"]) == 0
	assert "Dry run, nothing was changed" in capsys.readouterr().out
	assert Package.query.filter_by(name="imported_mod").count() == 0

	assert script.main([path]) == 0
	out = capsys.readouterr().out
	assert "Packages: 2 created, 0 already existed" in out
	assert "Import complete" in out
	assert Package.query.filter_by(name="imported_mod").count() == 1

	assert script.main([os.path.join(str(upload_dir), "missing.zip")]) == 1
	assert script.main([]) == 2
