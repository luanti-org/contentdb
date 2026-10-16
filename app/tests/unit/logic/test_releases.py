# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

import io
from typing import List
from zipfile import ZipFile

from werkzeug.datastructures import FileStorage

from app.domain.releases import _zip_contains_git_dir


def make_zip(names: List[str]) -> FileStorage:
	data = io.BytesIO()
	with ZipFile(data, "w") as zf:
		for name in names:
			zf.writestr(name, "content")
	data.seek(0)
	return FileStorage(data, filename="release.zip")


def test_git_folder():
	assert _zip_contains_git_dir(make_zip(["mymod/init.lua", "mymod/.git/HEAD"]))
	assert _zip_contains_git_dir(make_zip([".git/config"]))


def test_git_file():
	assert _zip_contains_git_dir(make_zip(["mymod/init.lua", "mymod/submodule/.git"]))
	assert _zip_contains_git_dir(make_zip([".git"]))


def test_git_folder_backslashes():
	assert _zip_contains_git_dir(make_zip(["mymod\\.git\\HEAD"]))


def test_no_git():
	assert not _zip_contains_git_dir(make_zip(["mymod/init.lua", "mymod/mod.conf"]))
	assert not _zip_contains_git_dir(make_zip([
		"mymod/.gitignore",
		"mymod/.gitattributes",
		"mymod/.github/workflows/test.yml",
		"mymod/foo.git",
		"mymod/.git_old/HEAD",
	]))


def test_bad_zip():
	file = FileStorage(io.BytesIO(b"not a zip file"), filename="release.zip")
	assert not _zip_contains_git_dir(file)
	assert file.stream.tell() == 0


def test_stream_rewound():
	file = make_zip(["mymod/init.lua", "mymod/.git/HEAD"])
	_zip_contains_git_dir(file)
	assert file.stream.tell() == 0

	file = make_zip(["mymod/init.lua"])
	_zip_contains_git_dir(file)
	assert file.stream.tell() == 0
