# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2026 rubenwardy <rw@rubenwardy>

import magic
import os
from werkzeug.datastructures import FileStorage

from flask_babel import lazy_gettext, LazyString
from typing import Optional

from app import app
from app.domain.DomainError import DomainError
from app.utils.misc import random_string

upload_method = app.config["UPLOAD_METHOD"]

if upload_method == "local":
	from .local import backend_upload_file, backend_copy_upload, backend_get_public_upload_url, backend_get_upload_local_path, backend_get_thumbnail_url, backend_delete_upload
elif upload_method == "bunny":
	from .bunny import backend_upload_file, backend_copy_upload, backend_get_public_upload_url, backend_get_upload_local_path, backend_get_thumbnail_url, backend_delete_upload
else:
	raise Exception("Invalid UPLOAD_METHOD")


def get_extension(filename):
	return filename.rsplit(".", 1)[1].lower() if "." in filename else None


ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/webp"}


def is_allowed_image(data):
	mime = magic.from_buffer(data, mime=True)
	return mime in ALLOWED_IMAGES


def upload_file(file: FileStorage, file_type: str, file_type_desc: LazyString | str, length: int=10):
	if not file or file is None or file.filename == "":
		raise DomainError(400, "Expected file")

	is_image = False
	if file_type == "image":
		allowed_extensions = ["jpg", "png", "webp"]
		is_image = True
	elif file_type == "zip":
		allowed_extensions = ["zip"]
	else:
		raise Exception("Invalid fileType")

	ext = get_extension(file.filename)
	if ext == "jpeg":
		ext = "jpg"

	if ext is None or ext not in allowed_extensions:
		raise DomainError(400, lazy_gettext("Please upload %(file_desc)s", file_desc=file_type_desc))

	if is_image and not is_allowed_image(file.stream.read()):
		raise DomainError(400, lazy_gettext("Uploaded image isn't actually an image"))

	file.stream.seek(0)
	result_path = backend_upload_file(file, file_type, ext, length)
	file.stream.seek(0)
	return result_path, get_upload_local_path(result_path)


def copy_to_uploads(filepath: str):
	return backend_copy_upload(filepath), get_upload_local_path(result_path)


def get_public_upload_url(filepath: str):
	return backend_get_public_upload_url(filepath)


def get_upload_local_path(filepath: str):
	return backend_get_upload_local_path(filepath)


def get_thumbnail_url(filepath: str, thumbnail_level: int, format: Optional[str] = None):
	return backend_get_thumbnail_url(filepath, thumbnail_level, format)


def delete_upload(filepath: str):
	return backend_delete_upload(filepath)


@app.route("/uploads/<path:path>")
def send_upload(path):
	if upload_method == "local":
		return send_from_directory(app.config["UPLOAD_DIR"], path)
	elif upload_method == "bunny":
		return redirect(backend_get_public_upload_url(path))
	else:
		raise Exception("Invalid UPLOAD_METHOD")
