# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from zipfile import ZipFile, ZipInfo

import pytest

from app.tasks import TaskError
from app.utils import zip as zip_utils
from app.utils.zip import check_zip_file, safe_extract_zip, ZipCheckResult


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
	archive = make_zip(tmp_path, {f"file{i}.txt": "" for i in range(len(sizes))})
	with ZipFile(archive, "r") as zf:
		for info, size in zip(zf.infolist(), sizes, strict=True):
			info.file_size = size
		return check_zip_file(str(make_temp_dir(tmp_path)), zf)


def check_patched_zip(tmp_path, files, patch):
	archive = tmp_path / "test.zip"
	with ZipFile(archive, "w") as zf:
		for filename, content in files.items():
			zf.writestr(filename, content)
		patch(zf.filelist)

	with ZipFile(archive, "r") as zf:
		return check_zip_file(str(make_temp_dir(tmp_path)), zf)


def test_check_zip_file_allows_inside(tmp_path):
	assert check_zip(tmp_path, "mod.conf", "textures/a.png", "a/../b.txt") == ZipCheckResult.OK


def test_check_zip_file_allows_empty(tmp_path):
	assert check_zip(tmp_path) == ZipCheckResult.OK


def test_check_zip_file_rejects_outside(tmp_path):
	assert check_zip(tmp_path, "../evil.txt") == ZipCheckResult.PATH_TRAVERSAL
	assert check_zip(tmp_path, "/etc/evil.txt") == ZipCheckResult.PATH_TRAVERSAL


def test_check_zip_file_rejects_sibling_prefix(tmp_path):
	assert check_zip(tmp_path, "../abcd/evil.txt") == ZipCheckResult.PATH_TRAVERSAL


def test_check_zip_file_rejects_newline(tmp_path):
	assert check_zip(tmp_path, "mod.conf", "bad\nname.txt") == ZipCheckResult.INVALID_NAME


def test_check_zip_file_rejects_control_characters(tmp_path):
	assert check_zip(tmp_path, "mod.conf", "bad\tname.txt") == ZipCheckResult.INVALID_NAME


def test_check_zip_file_rejects_nul(tmp_path):
	# ZipInfo truncates names at NUL when writing, so patch the bytes
	archive = make_zip(tmp_path, {"mod.conf": "", "badXname.txt": ""})
	archive.write_bytes(archive.read_bytes().replace(b"badXname.txt", b"bad\x00name.txt"))

	with ZipFile(archive, "r") as zf:
		assert check_zip_file(str(make_temp_dir(tmp_path)), zf) == ZipCheckResult.INVALID_NAME


def test_check_zip_file_backslashes(tmp_path):
	assert check_zip(tmp_path, "textures\\a.png") == ZipCheckResult.OK
	assert check_zip(tmp_path, "..\\evil.txt") == ZipCheckResult.PATH_TRAVERSAL
	assert check_zip(tmp_path, "a/..\\..\\evil.txt") == ZipCheckResult.PATH_TRAVERSAL
	assert check_zip(tmp_path, "\\evil.txt") == ZipCheckResult.PATH_TRAVERSAL


def test_check_zip_file_rejects_drive_letter(tmp_path):
	assert check_zip(tmp_path, "C:/evil.txt") == ZipCheckResult.INVALID_NAME
	assert check_zip(tmp_path, "C:\\evil.txt") == ZipCheckResult.INVALID_NAME


def test_check_zip_file_rejects_symlink_and_special(tmp_path):
	for mode in (0o120777, 0o010644, 0o060644):
		info = ZipInfo("link")
		info.create_system = 3
		info.external_attr = mode << 16
		archive = tmp_path / "test.zip"
		with ZipFile(archive, "w") as zf:
			zf.writestr(info, "target")
		with ZipFile(archive, "r") as zf:
			assert check_zip_file(str(make_temp_dir(tmp_path)), zf) == ZipCheckResult.UNSUPPORTED_ENTRY


def test_check_zip_file_allows_regular_modes(tmp_path):
	for mode in (0o100644, 0o100755, 0o040755):
		info = ZipInfo("file")
		info.create_system = 3
		info.external_attr = mode << 16
		archive = tmp_path / "test.zip"
		with ZipFile(archive, "w") as zf:
			zf.writestr(info, "")
		with ZipFile(archive, "r") as zf:
			assert check_zip_file(str(make_temp_dir(tmp_path)), zf) == ZipCheckResult.OK


def test_check_zip_file_rejects_encrypted(tmp_path):
	def patch(infos):
		infos[0].flag_bits |= 0x1

	assert check_patched_zip(tmp_path, {"a.txt": "a"}, patch) == ZipCheckResult.UNSUPPORTED_ENTRY


def test_check_zip_file_entry_limit(tmp_path, monkeypatch):
	monkeypatch.setattr(zip_utils, "MAX_ARCHIVE_FILES", 2)
	assert check_zip(tmp_path, "a", "b") == ZipCheckResult.OK
	assert check_zip(tmp_path, "a", "b", "c") == ZipCheckResult.TOO_MANY_ENTRIES


def test_check_zip_file_rejects_local_header_name_mismatch(tmp_path):
	archive = make_zip(tmp_path, {"aaaa.txt": "a", "other.txt": "b"})
	data = archive.read_bytes()
	archive.write_bytes(data.replace(b"aaaa.txt", b"bbbb.txt", 1))

	with ZipFile(archive, "r") as zf:
		assert check_zip_file(str(make_temp_dir(tmp_path)), zf) == ZipCheckResult.MALFORMED


def test_check_zip_file_rejects_overlapping_entries(tmp_path, capsys):
	def patch(infos):
		infos[1].header_offset = infos[0].header_offset

	archive = tmp_path / "test.zip"
	with ZipFile(archive, "w") as zf, pytest.warns(UserWarning):
		zf.writestr("a.txt", "a" * 100)
		zf.writestr("a.txt", "b" * 100)
		patch(zf.filelist)

	with ZipFile(archive, "r") as zf:
		assert check_zip_file(str(make_temp_dir(tmp_path)), zf) == ZipCheckResult.MALFORMED
	assert "overlaps" in capsys.readouterr().err


def test_check_zip_file_rejects_entry_running_into_directory(tmp_path):
	def patch(infos):
		infos[0].compress_size += 1

	assert check_patched_zip(tmp_path, {"a.txt": "a"}, patch) == ZipCheckResult.MALFORMED


def test_check_zip_file_rejects_entry_past_end(tmp_path):
	def patch(infos):
		infos[0].compress_size += 1000

	assert check_patched_zip(tmp_path, {"a.txt": "a"}, patch) == ZipCheckResult.MALFORMED


def test_check_zip_file_size_limit(tmp_path):
	limit = 300 * 1024 * 1024
	assert check_zip_sizes(tmp_path, limit) == ZipCheckResult.OK
	assert check_zip_sizes(tmp_path, limit // 2, limit // 2) == ZipCheckResult.OK
	assert check_zip_sizes(tmp_path, limit + 1) == ZipCheckResult.TOO_LARGE
	assert check_zip_sizes(tmp_path, limit // 2, limit // 2, 1) == ZipCheckResult.TOO_LARGE


def test_safe_extract_zip_extracts(tmp_path):
	temp_dir = make_temp_dir(tmp_path)
	archive = make_zip(tmp_path, {
		"mod.conf": "name = mymod\n",
		"textures/a.png": "png",
	})

	assert safe_extract_zip(str(temp_dir), str(archive)) == ZipCheckResult.OK
	assert (temp_dir / "mod.conf").read_text() == "name = mymod\n"
	assert (temp_dir / "textures" / "a.png").read_text() == "png"


def test_safe_extract_zip_rejects_unsafe_without_extracting(tmp_path):
	temp_dir = make_temp_dir(tmp_path)
	archive = make_zip(tmp_path, {
		"mod.conf": "name = mymod\n",
		"../abcd/evil.txt": "evil",
	})

	assert safe_extract_zip(str(temp_dir), str(archive)) == ZipCheckResult.PATH_TRAVERSAL
	assert list(temp_dir.iterdir()) == []
	assert not (tmp_path / "abcd").exists()


def test_safe_extract_zip_bad_zip(tmp_path):
	temp_dir = make_temp_dir(tmp_path)
	archive = tmp_path / "test.zip"
	archive.write_text("not a zip file")

	with pytest.raises(TaskError) as exc_info:
		safe_extract_zip(str(temp_dir), str(archive))

	assert exc_info.value.value == "Invalid zip"


def test_safe_extract_zip_unsupported_compression(tmp_path):
	temp_dir = make_temp_dir(tmp_path)
	archive = tmp_path / "test.zip"
	with ZipFile(archive, "w") as zf:
		zf.writestr("a.txt", "a")
		zf.filelist[0].compress_type = 99

	with pytest.raises(TaskError) as exc_info:
		safe_extract_zip(str(temp_dir), str(archive))

	assert exc_info.value.value == "Invalid zip"
