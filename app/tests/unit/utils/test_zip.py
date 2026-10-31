# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from unittest.mock import MagicMock
from zipfile import ZipFile, ZipInfo

import pytest

from app.tasks import TaskError
from app.utils.zip import check_zip_file, safe_extract_zip


def make_temp_dir(tmp_path):
	temp_dir = tmp_path / "abc"
	temp_dir.mkdir(exist_ok=True)
	return temp_dir


def make_zip(tmp_path, files):
	archive = tmp_path / "test.zip"
	with ZipFile(archive, "w") as zf:
		for filename, content in files.items():
			zf.writestr(filename, content)

	return archive


def check_zip(tmp_path, *filenames):
	temp_dir = make_temp_dir(tmp_path)
	archive = make_zip(tmp_path, {filename: "" for filename in filenames})
	with ZipFile(archive, "r") as zf:
		return check_zip_file(str(temp_dir), zf)


def check_zip_sizes(tmp_path, *sizes):
	infos = []
	for i, size in enumerate(sizes):
		info = ZipInfo(f"file{i}.txt")
		info.file_size = size
		infos.append(info)

	zf = MagicMock()
	zf.infolist.return_value = infos
	return check_zip_file(str(make_temp_dir(tmp_path)), zf)


def test_check_zip_file_allows_inside(tmp_path):
	assert check_zip(tmp_path, "mod.conf", "textures/a.png", "a/../b.txt")


def test_check_zip_file_allows_empty(tmp_path):
	assert check_zip(tmp_path)


def test_check_zip_file_rejects_outside(tmp_path):
	assert not check_zip(tmp_path, "../evil.txt")
	assert not check_zip(tmp_path, "/etc/evil.txt")


def test_check_zip_file_rejects_sibling_prefix(tmp_path):
	assert not check_zip(tmp_path, "../abcd/evil.txt")


def test_check_zip_file_rejects_newline(tmp_path):
	assert not check_zip(tmp_path, "mod.conf", "bad\nname.txt")


def test_check_zip_file_size_limit(tmp_path):
	limit = 300 * 1024 * 1024
	assert check_zip_sizes(tmp_path, limit)
	assert check_zip_sizes(tmp_path, limit // 2, limit // 2)
	assert not check_zip_sizes(tmp_path, limit + 1)
	assert not check_zip_sizes(tmp_path, limit // 2, limit // 2, 1)


def test_safe_extract_zip_extracts(tmp_path):
	temp_dir = make_temp_dir(tmp_path)
	archive = make_zip(tmp_path, {
		"mod.conf": "name = mymod\n",
		"textures/a.png": "png",
	})

	assert safe_extract_zip(str(temp_dir), str(archive))
	assert (temp_dir / "mod.conf").read_text() == "name = mymod\n"
	assert (temp_dir / "textures" / "a.png").read_text() == "png"


def test_safe_extract_zip_rejects_unsafe_without_extracting(tmp_path):
	temp_dir = make_temp_dir(tmp_path)
	archive = make_zip(tmp_path, {
		"mod.conf": "name = mymod\n",
		"../abcd/evil.txt": "evil",
	})

	assert not safe_extract_zip(str(temp_dir), str(archive))
	assert list(temp_dir.iterdir()) == []
	assert not (tmp_path / "abcd").exists()


def test_safe_extract_zip_bad_zip(tmp_path):
	temp_dir = make_temp_dir(tmp_path)
	archive = tmp_path / "test.zip"
	archive.write_text("not a zip file")

	with pytest.raises(TaskError):
		safe_extract_zip(str(temp_dir), str(archive))
