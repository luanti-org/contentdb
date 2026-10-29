# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os
import requests
import tempfile

from app import app
import shutil
from app.utils.files import prune_dir
from app.utils.misc import random_string
from typing import Optional


public_url = app.config["UPLOAD_PUBLIC_URL"]
storage_name = app.config["UPLOAD_BUNNY_STORAGE"]
access_key = app.config["UPLOAD_BUNNY_ACCESS_KEY"]
cache_dir_path = os.path.join(tempfile.gettempdir(), "contentdb-uploads")
os.makedirs(cache_dir_path, exist_ok=True)

# Cached files that haven't been used for this long are deleted when a new file is cached
CACHE_MAX_AGE = 24 * 60 * 60


def _upload_file(filepath: str) -> str:
	filename = os.path.basename(filepath)
	upload_path = f"/uploads/{filename}"
	url = f"https://storage.bunnycdn.com/{storage_name}/{upload_path}"
	with open(filepath, "rb") as f:
		response = requests.put(
			url,
			headers={
				"AccessKey": access_key,
				"Content-Type": "application/octet-stream"
			},
			data=f.read(),
		)
		response.raise_for_status()
	return upload_path


def _download_file(upload_path: str) -> str:
	prune_dir(cache_dir_path, CACHE_MAX_AGE)
	download_path = os.path.join(cache_dir_path, os.path.basename(upload_path))
	url = f"https://storage.bunnycdn.com/{storage_name}/{upload_path}"
	response = requests.get(
		url,
		headers={
			"AccessKey": access_key,
		}
	)
	response.raise_for_status()

	# Write to a temporary name first so other processes never see a partial file
	partial_path = f"{download_path}.{random_string(10)}.partial"
	try:
		with open(partial_path, "wb") as f:
			f.write(response.content)
		os.replace(partial_path, download_path)
	finally:
		if os.path.exists(partial_path):
			os.remove(partial_path)

	return download_path


def _delete_file(upload_path: str):
	url = f"https://storage.bunnycdn.com/{storage_name}/{upload_path}"
	response = requests.delete(
		url,
		headers={
			"AccessKey": access_key,
		}
	)
	response.raise_for_status()


def backend_upload_file(file, file_type: str, ext: str, length: int=10) -> str:
	prune_dir(cache_dir_path, CACHE_MAX_AGE)
	filename = f"{random_string(length)}.{ext}"
	file_path = os.path.join(cache_dir_path, filename)
	file.save(file_path)
	return _upload_file(file_path)


def backend_copy_upload(filepath: str) -> str:
	prune_dir(cache_dir_path, CACHE_MAX_AGE)
	ext = os.path.splitext(filepath)[1][1:]
	filename = f"{random_string(10)}.{ext}"
	cache_file_path = os.path.join(cache_dir_path, filename)
	shutil.copy(filepath, cache_file_path)
	return _upload_file(cache_file_path)


def backend_get_public_upload_url(upload_path: str) -> str:
	filename = os.path.basename(upload_path)
	return public_url.rstrip("/") + "/" + filename


def backend_get_upload_local_path(upload_path: str) -> Optional[str]:
	file_path = os.path.join(cache_dir_path, os.path.basename(upload_path))
	try:
		# Mark as recently used, so it isn't pruned
		os.utime(file_path)
		return file_path
	except FileNotFoundError:
		return _download_file(upload_path)


LEVELS = [
	(100, "3:2"),
	(270, "3:2"),
	(350, "3:2"),
	(1100, "16:9"),
]


def backend_get_thumbnail_url(upload_path: str, thumbnail_level: int, format: Optional[str] = None):
	if thumbnail_level > len(LEVELS) or thumbnail_level <= 0:
		raise ValueError("Invalid thumbnail level")
	(width, ratio) = LEVELS[thumbnail_level - 1]
	url = backend_get_public_upload_url(upload_path)
	url = f"{url}?width={width}&aspect_ratio={ratio}"
	if format:
		url = f"{url}&format={format}"
	return url


def backend_delete_upload(upload_path: str) -> None:
	_delete_file(upload_path)


def backend_get_checksums(upload_paths: list[str]) -> dict[str, str]:
	url = f"https://storage.bunnycdn.com/{storage_name}/uploads/"
	response = requests.get(
		url,
		headers={
			"AccessKey": access_key,
			"Accept": "application/json",
		},
		timeout=300,
	)
	response.raise_for_status()

	checksums = {}
	for obj in response.json():
		if not obj["IsDirectory"] and obj["Checksum"]:
			checksums[f"/uploads/{obj['ObjectName']}"] = obj["Checksum"].lower()

	return {path: checksums[path] for path in upload_paths if path in checksums}
