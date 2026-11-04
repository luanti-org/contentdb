# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
import json
import os
import zipfile

import pytest

from app.default_data import populate_test_data
from app.models import db, User, Dependency, MetaPackage
from app.tasks.dumptask import create_database_dump
from app.uploads import copy_to_uploads, local
from .utils import make_package
from .utils import client # noqa


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
		assert "created_at" in json.loads(zipf.read("backup/index.json"))
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
