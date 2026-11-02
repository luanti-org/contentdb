# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import os
import sys
from zipfile import ZipFile, BadZipFile

from app.tasks import TaskError


def check_zip_file(temp_dir: str, zf: ZipFile) -> bool:
	# No more than 300MB
	total_size = sum(e.file_size for e in zf.infolist())
	if total_size > 300 * 1024 * 1024:
		print(f"zip file is too large: {total_size} bytes", file=sys.stderr)
		return False

	# Check paths
	real_temp_dir = os.path.realpath(temp_dir)
	for member in zf.infolist():
		# We've had cases of newlines in filenames
		if "\n" in member.filename:
			print("zip file member contains invalid characters", file=sys.stderr)
			return False

		file_path = os.path.realpath(os.path.join(temp_dir, member.filename))
		if os.path.commonpath([real_temp_dir, file_path]) != real_temp_dir:
			print(f"zip file contains path out-of-bounds: {file_path}", file=sys.stderr)
			return False

	return True


def safe_extract_zip(temp_dir: str, archive_path: str) -> bool:
	try:
		with ZipFile(archive_path, 'r') as zf:
			if not check_zip_file(temp_dir, zf):
				return False

			# Extract all
			for member in zf.infolist():
				zf.extract(member, temp_dir)
	except BadZipFile as e:
		raise TaskError(str(e)) from e

	return True
