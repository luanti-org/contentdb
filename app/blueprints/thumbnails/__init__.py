# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import re
import requests
from flask import abort, send_file, Blueprint, current_app, request
import os
from PIL import Image


bp = Blueprint("thumbnails", __name__)


ALLOWED_RESOLUTIONS = [(100, 67), (270, 180), (350, 233), (1100, 520)]
ALLOWED_MIMETYPES = {
	"png": "image/png",
	"webp": "image/webp",
	"jpg": "image/jpeg",
}


def mkdir(path):
	assert path != "" and path is not None
	try:
		if not os.path.isdir(path):
			os.mkdir(path)
	except FileExistsError:
		pass


def resize_and_crop(img_path, modified_path, size):
	with Image.open(img_path) as img:
		# Get current and desired ratio for the images
		img_ratio = img.size[0] / float(img.size[1])
		desired_ratio = size[0] / float(size[1])

		# Is more portrait than target, scale and crop
		if desired_ratio > img_ratio:
			img = img.resize((int(size[0]), int(size[0] * img.size[1] / img.size[0])),
					Image.BICUBIC)
			box = (0, (img.size[1] - size[1]) / 2, img.size[0], (img.size[1] + size[1]) / 2)
			img = img.crop(box)

		# Is more landscape than target, scale and crop
		elif desired_ratio < img_ratio:
			img = img.resize((int(size[1] * img.size[0] / img.size[1]), int(size[1])),
					Image.BICUBIC)
			box = ((img.size[0] - size[0]) / 2, 0, (img.size[0] + size[0]) / 2, img.size[1])
			img = img.crop(box)

		# Is exactly the same ratio as target
		else:
			img = img.resize(size, Image.BICUBIC)

		if modified_path.endswith(".jpg") and img.mode != "RGB":
			img = img.convert("RGB")

		img.save(modified_path, lossless=True)


def find_source_file(img):
	upload_dir = current_app.config["UPLOAD_DIR"]
	source_filepath = os.path.join(upload_dir, img)
	if os.path.isfile(source_filepath):
		return source_filepath

	period = source_filepath.rfind(".")
	start = source_filepath[:period]
	ext = source_filepath[period + 1:]
	if ext not in ALLOWED_MIMETYPES:
		abort(404)

	for other_ext in ALLOWED_MIMETYPES.keys():
		other_path = f"{start}.{other_ext}"
		if ext != other_ext and os.path.isfile(other_path):
			return other_path

	abort(404)


def get_mimetype(cache_filepath: str) -> str:
	period = cache_filepath.rfind(".")
	ext = cache_filepath[period + 1:]
	mimetype = ALLOWED_MIMETYPES.get(ext)
	if mimetype is None:
		abort(404)
	return mimetype


@bp.route("/thumbnails/<int:level>/<img>")
def make_thumbnail(img, level):
	if level > len(ALLOWED_RESOLUTIONS) or level <= 0:
		abort(403)
	w, h = ALLOWED_RESOLUTIONS[level - 1]

	thumbnail_dir = current_app.config["THUMBNAIL_DIR"]
	mkdir(thumbnail_dir)

	output_dir = os.path.join(thumbnail_dir, str(level))
	mkdir(output_dir)

	cache_filepath = os.path.join(output_dir, img)
	if not os.path.isfile(cache_filepath):
		source_filepath = find_source_file(img)
		resize_and_crop(source_filepath, cache_filepath, (w, h))

	res = send_file(cache_filepath, mimetype=get_mimetype(cache_filepath))
	res.headers["Cache-Control"] = "max-age=604800" # 1 week
	return res


@bp.route("/thumbnails/youtube/<id_>.jpg")
def youtube(id_: str):
	if not re.match(r"^[A-Za-z0-9\-_]+$", id_):
		abort(400)

	cache_dir = os.path.join(current_app.config["THUMBNAIL_DIR"], "youtube")
	os.makedirs(cache_dir, exist_ok=True)
	cache_filepath = os.path.join(cache_dir, id_ + ".jpg")

	url = f"https://img.youtube.com/vi/{id_}/default.jpg"

	response = requests.get(url, stream=True)
	if response.status_code != 200:
		abort(response.status_code)

	with open(cache_filepath, "wb") as file:
		file.write(response.content)

	res = send_file(cache_filepath)
	res.headers["Cache-Control"] = "max-age=604800"  # 1 week
	return res
