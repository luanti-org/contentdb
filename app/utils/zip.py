# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import enum
import os
import sys
from zipfile import ZipFile, BadZipFile

from app.tasks import TaskError


class ZipCheckResult(enum.Enum):
	OK = "ok"
	TOO_LARGE = "too large"
	INVALID_NAME = "invalid name"
	# Can't be made by accident, so is treated as malicious
	PATH_TRAVERSAL = "path traversal"

	@property
	def is_ok(self) -> bool:
		return self == ZipCheckResult.OK


def check_zip_file(temp_dir: str, zf: ZipFile) -> ZipCheckResult:
	# No more than 300MB
	total_size = sum(e.file_size for e in zf.infolist())
	if total_size > 300 * 1024 * 1024:
		print(f"zip file is too large: {total_size} bytes", file=sys.stderr)
		return ZipCheckResult.TOO_LARGE

	# Check paths
	real_temp_dir = os.path.realpath(temp_dir)
	for member in zf.infolist():
		# We've had cases of newlines in filenames
		if "\n" in member.filename:
			print("zip file member contains invalid characters", file=sys.stderr)
			return ZipCheckResult.INVALID_NAME

		file_path = os.path.realpath(os.path.join(temp_dir, member.filename))
		if os.path.commonpath([real_temp_dir, file_path]) != real_temp_dir:
			print(f"zip file contains path out-of-bounds: {file_path}", file=sys.stderr)
			return ZipCheckResult.PATH_TRAVERSAL

	return ZipCheckResult.OK


def safe_extract_zip(temp_dir: str, archive_path: str) -> ZipCheckResult:
	try:
		with ZipFile(archive_path, 'r') as zf:
			result = check_zip_file(temp_dir, zf)
			if not result.is_ok:
				return result

			# Extract all
			for member in zf.infolist():
				zf.extract(member, temp_dir)
	except BadZipFile as e:
		raise TaskError(str(e)) from e

	return ZipCheckResult.OK
