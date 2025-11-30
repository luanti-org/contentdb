# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import imghdr
import os

from flask_babel import lazy_gettext, LazyString

from app import app
from app.logic.LogicError import LogicError
from app.utils import random_string


def get_extension(filename):
	return filename.rsplit(".", 1)[1].lower() if "." in filename else None


ALLOWED_IMAGES = {"jpeg", "png", "webp"}


def is_allowed_image(data):
	return imghdr.what(None, data) in ALLOWED_IMAGES


def upload_file(file, file_type: str, file_type_desc: LazyString | str, length: int=10):
	if not file or file is None or file.filename == "":
		raise LogicError(400, "Expected file")

	assert os.path.isdir(app.config["UPLOAD_DIR"]), "UPLOAD_DIR must exist"

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
		raise LogicError(400, lazy_gettext("Please upload %(file_desc)s", file_desc=file_type_desc))

	if is_image and not is_allowed_image(file.stream.read()):
		raise LogicError(400, lazy_gettext("Uploaded image isn't actually an image"))

	file.stream.seek(0)

	filename = random_string(length) + "." + ext
	filepath = os.path.join(app.config["UPLOAD_DIR"], filename)
	file.save(filepath)

	return "/uploads/" + filename, filepath
