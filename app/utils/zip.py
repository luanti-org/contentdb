# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import os
import re
import stat
import struct
import sys
import zlib
from typing import Optional
from zipfile import ZipFile, ZipInfo, BadZipFile

from app.tasks import TaskError
from app.utils.git import MAX_ARCHIVE_FILES

DRIVE_PATH = re.compile(r"^[A-Za-z]:")


def _member_problem(temp_dir: str, real_temp_dir: str, member: ZipInfo) -> Optional[str]:
	name = member.filename

	# We've had cases of newlines in filenames. orig_filename as ZipInfo truncates filename at NUL
	if any(ord(c) < 32 for c in member.orig_filename):
		return "contains control characters"

	if member.flag_bits & 0x1:
		return "is encrypted"

	mode = member.external_attr >> 16
	if member.create_system == 3 and mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
		return "is not a regular file or directory"

	# Backslashes are separators on Windows
	normalized = name.replace("\\", "/")
	if DRIVE_PATH.match(normalized):
		return "has a drive letter"

	for candidate in (name, normalized):
		file_path = os.path.realpath(os.path.join(temp_dir, candidate))
		if os.path.commonpath([real_temp_dir, file_path]) != real_temp_dir:
			return "is out-of-bounds"

	return None


def _layout_problem(zf: ZipFile) -> Optional[str]:
	fp = zf.fp
	assert fp is not None
	spans = []
	for info in zf.infolist():
		fp.seek(info.header_offset)
		header = fp.read(30)
		if len(header) < 30 or header[:4] != b"PK\x03\x04":
			return f"{info.filename!r} has a bad local header"

		name_len, extra_len = struct.unpack("<HH", header[26:30])
		encoding = "utf-8" if info.flag_bits & 0x800 else "cp437"
		if fp.read(name_len).decode(encoding, "replace") != info.orig_filename:
			return f"{info.filename!r} has a different name in its local header"

		end = info.header_offset + 30 + name_len + extra_len + info.compress_size
		if end > zf.start_dir:
			return f"{info.filename!r} runs into the central directory"

		spans.append((info.header_offset, end, info.filename))

	spans.sort()
	for (_, prev_end, _), (start, _, name) in zip(spans, spans[1:], strict=False):
		if start < prev_end:
			return f"{name!r} overlaps another entry"

	return None


def check_zip_file(temp_dir: str, zf: ZipFile) -> bool:
	infos = zf.infolist()

	# No more than 300MB
	total_size = sum(e.file_size for e in infos)
	if total_size > 300 * 1024 * 1024:
		print(f"zip file is too large: {total_size} bytes", file=sys.stderr)
		return False

	if len(infos) > MAX_ARCHIVE_FILES:
		print(f"zip file has too many entries: {len(infos)}", file=sys.stderr)
		return False

	real_temp_dir = os.path.realpath(temp_dir)
	for member in infos:
		problem = _member_problem(temp_dir, real_temp_dir, member)
		if problem:
			print(f"zip file member {member.filename!r} {problem}", file=sys.stderr)
			return False

	problem = _layout_problem(zf)
	if problem:
		print(f"zip file is malformed: {problem}", file=sys.stderr)
		return False

	return True


# Details of why a zip is invalid go to stderr, not the error, to not help attackers
def safe_extract_zip(temp_dir: str, archive_path: str):
	try:
		with ZipFile(archive_path, 'r') as zf:
			if not check_zip_file(temp_dir, zf):
				raise TaskError("Invalid zip")

			# Extract all
			for member in zf.infolist():
				zf.extract(member, temp_dir)
	except (BadZipFile, zlib.error, NotImplementedError, EOFError) as e:
		print(f"bad zip file: {e!r}", file=sys.stderr)
		raise TaskError("Invalid zip") from e
