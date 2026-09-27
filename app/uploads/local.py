# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os
import shutil

from app import app
from app.utils.misc import random_string
from typing import Optional


upload_dir = app.config["UPLOAD_DIR"]


def backend_upload_file(file, file_type: str, ext: str, length: int=10):
	assert os.path.isdir(app.config["UPLOAD_DIR"]), "UPLOAD_DIR must exist"

	filename = random_string(length) + "." + ext
	filepath = os.path.join(upload_dir, filename)
	file.save(filepath)
	return "/uploads/" + filename


def backend_copy_upload(filepath: str) -> str:
	ext = os.path.splitext(filepath)[1][1:]
	filename = random_string(10) + "." + ext
	destPath = os.path.join(upload_dir, filename)
	shutil.copyfile(filepath, destPath)
	return "/uploads/" + filename


def backend_get_public_upload_url(filepath: str) -> str:
	return filepath


def backend_get_upload_local_path(filepath: str) -> Optional[str]:
	filename = os.path.basename(filepath)
	path = os.path.join(upload_dir, filename)
	if os.path.isfile(path):
		return path
	else:
		return None


def backend_get_thumbnail_url(filepath: str, thumbnail_level: int, format: Optional[str] = None):
	filename = os.path.basename(filepath)
	url = f"/thumbnails/{thumbnail_level}/{filename}"
	if format is not None:
		start = url[:url.rfind(".")]
		url = f"{start}.{format}"
	return url


def backend_delete_upload(filepath: str) -> bool:
	filename = os.path.basename(filepath)
	os.remove(os.path.join(upload_dir, filename))
