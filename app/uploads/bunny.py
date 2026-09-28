# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os
import requests
import tempfile

from app import app
from app.utils.misc import random_string
from typing import Optional


public_url = app.config["UPLOAD_PUBLIC_URL"]
storage_name = app.config["UPLOAD_BUNNY_STORAGE"]
access_key = app.config["UPLOAD_BUNNY_ACCESS_KEY"]
cache_dir_path = os.path.join(tempfile.gettempdir(), "contentdb-uploads")
os.makedirs(cache_dir_path, exist_ok=True)


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
	download_path = os.path.join(cache_dir_path, os.path.basename(upload_path))
	url = f"https://storage.bunnycdn.com/{storage_name}/{upload_path}"
	response = requests.get(
		url,
		headers={
			"AccessKey": access_key,
		}
	)
	response.raise_for_status()
	with open(download_path, "wb") as f:
		f.write(r.content)
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
	filename = f"{random_string(length)}.{ext}"
	file_path = os.path.join(cache_dir_path, filename)
	file.save(file_path)
	return _upload_file(file_path)


def backend_copy_upload(filepath: str) -> str:
	filename = f"{random_string(length)}.{ext}"
	cache_file_path = os.path.join(cache_dir_path, filename)
	shutil.copy(filepath, cache_file_path)
	return _upload_file(cache_file_path)


def backend_get_public_upload_url(filepath: str) -> str:
	filename = os.path.basename(filepath)
	return public_url.rstrip("/") + "/" + filename


def backend_get_upload_local_path(upload_path: str) -> Optional[str]:
	file_path = os.path.join(cache_dir_path, os.path.basename(upload_path))
	if os.path.exists(file_path):
		return file_path
	return _download_file(upload_path)


def backend_get_thumbnail_url(filepath: str, thumbnail_level: int, format: Optional[str] = None):
	thumbnail_class = f"L{thumbnail_level}"
	url = backend_get_public_upload_url(filepath)
	url = f"{url}?class={thumbnail_class}"
	if format:
		url = f"{url}&format={format}"
	return url


def backend_delete_upload(filepath: str):
	_delete_file(filepath)
