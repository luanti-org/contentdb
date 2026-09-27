# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os

from app import app
from app.utils.misc import random_string
from typing import Optional


public_url = app.config["UPLOAD_PUBLIC_URL"]


def backend_upload_file(file, file_type: str, ext: str, length: int=10) -> str:
	pass


def backend_copy_upload(filepath: str) -> str:
	pass


def backend_get_public_upload_url(filepath: str) -> str:
	filename = os.path.basename(filepath)
	return public_url.rstrip("/") + "/" + filename


def backend_get_upload_local_path(filepath: str) -> Optional[str]:
	pass


def backend_get_thumbnail_url(filepath: str, thumbnail_level: int, format: Optional[str] = None):
	thumbnail_class = f"L{thumbnail_level}"
	url = backend_get_public_upload_url(filepath)
	url = f"{url}?class={thumbnail_class}"
	if format:
		url = f"{url}&format={format}"
	return url


def backend_delete_upload(filepath: str) -> bool:
	pass
