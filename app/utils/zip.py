# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import os
from zipfile import ZipFile, BadZipFile

from app.tasks import TaskError, MaliciousContentError


def check_zip_file(temp_dir: str, zf: ZipFile):
	"""
	:raises MaliciousContentError: for path traversal, as it can't be made by accident
	:raises TaskError: for other problems
	"""
	# No more than 300MB
	total_size = sum(e.file_size for e in zf.infolist())
	if total_size > 300 * 1024 * 1024:
		raise TaskError(f"Zip file is too large: {total_size} bytes")

	# Check paths
	real_temp_dir = os.path.realpath(temp_dir)
	for member in zf.infolist():
		# We've had cases of newlines in filenames
		if "\n" in member.filename:
			raise TaskError(f"Zip file member contains invalid characters: {member.filename!r}")

		file_path = os.path.realpath(os.path.join(temp_dir, member.filename))
		if os.path.commonpath([real_temp_dir, file_path]) != real_temp_dir:
			raise MaliciousContentError(f"Zip file has path traversal: {member.filename!r}")


def safe_extract_zip(temp_dir: str, archive_path: str):
	"""
	Checks the zip with check_zip_file, and extracts it if it's safe.
	"""
	try:
		with ZipFile(archive_path, 'r') as zf:
			check_zip_file(temp_dir, zf)

			# Extract all
			for member in zf.infolist():
				zf.extract(member, temp_dir)
	except BadZipFile as e:
		raise TaskError(str(e)) from e
