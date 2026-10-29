# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os
import time

import pytest

from app.utils import files
from app.utils.files import get_temp_dir, prune_dir


def test_get_temp_dir_removed():
	with get_temp_dir() as temp:
		assert os.path.isdir(temp)
		with open(os.path.join(temp, "file.txt"), "w") as f:
			f.write("hello")

	assert not os.path.exists(temp)


def test_get_temp_dir_removed_on_error():
	with pytest.raises(RuntimeError):
		with get_temp_dir() as temp:
			raise RuntimeError("failed")

	assert not os.path.exists(temp)


def _make_file(path, age: float):
	with open(path, "w") as f:
		f.write("hello")
	mtime = time.time() - age
	os.utime(path, (mtime, mtime))


def test_prune_dir(tmp_path):
	_make_file(tmp_path / "old.zip", 2 * 60 * 60)
	_make_file(tmp_path / "new.zip", 10)
	os.mkdir(tmp_path / "subdir")
	os.utime(tmp_path / "subdir", (0, 0))

	prune_dir(str(tmp_path), 60 * 60)

	assert sorted(os.listdir(tmp_path)) == ["new.zip", "subdir"]


def test_prune_dir_ignores_concurrent_removal(tmp_path, monkeypatch):
	_make_file(tmp_path / "old.zip", 2 * 60 * 60)

	# Simulate another process deleting the file after it was listed
	real_remove = os.remove
	def remove_twice(path):
		real_remove(path)
		real_remove(path)

	monkeypatch.setattr(files.os, "remove", remove_twice)
	prune_dir(str(tmp_path), 60 * 60)

	assert os.listdir(tmp_path) == []
