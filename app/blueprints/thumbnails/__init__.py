# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import io
import re
import sys
import time

import requests
from flask import abort, send_file, Blueprint, current_app, request, redirect
import os
from PIL import Image

from app.models import User
from app.utils.files import prune_dir
from app.utils.gravatar import get_gravatar_url, get_gravatar_version
from app.utils.misc import random_string


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
	with Image.open(img_path) as source:
		img: Image.Image = source
		# Get current and desired ratio for the images
		img_ratio = img.size[0] / float(img.size[1])
		desired_ratio = size[0] / float(size[1])

		# Is more portrait than target, scale and crop
		if desired_ratio > img_ratio:
			img = img.resize((int(size[0]), int(size[0] * img.size[1] / img.size[0])),
					Image.Resampling.BICUBIC)
			box = (0, (img.size[1] - size[1]) / 2, img.size[0], (img.size[1] + size[1]) / 2)
			img = img.crop(box)

		# Is more landscape than target, scale and crop
		elif desired_ratio < img_ratio:
			img = img.resize((int(size[1] * img.size[0] / img.size[1]), int(size[1])),
					Image.Resampling.BICUBIC)
			box = ((img.size[0] - size[0]) / 2, 0, (img.size[0] + size[0]) / 2, img.size[1])
			img = img.crop(box)

		# Is exactly the same ratio as target
		else:
			img = img.resize(size, Image.Resampling.BICUBIC)

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
	if current_app.config.get("UPLOAD_METHOD") != "local":
		from app.uploads import get_thumbnail_url, remove_png_hack
		img = remove_png_hack(img)
		url = get_thumbnail_url(f"/uploads/{img}", level, format="png")
		return redirect(url)

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

	url = f"https://img.youtube.com/vi/{id_}/0.jpg"

	response = requests.get(url, stream=True, timeout=15)
	if response.status_code != 200:
		abort(response.status_code)

	with open(cache_filepath, "wb") as file:
		file.write(response.content)

	res = send_file(cache_filepath)
	res.headers["Cache-Control"] = "max-age=604800"  # 1 week
	return res


GRAVATAR_CACHE_MAX_AGE = 24 * 60 * 60  # 1 day
GRAVATAR_MAX_BYTES = 1000 * 1000
GRAVATAR_MAX_DIMENSION = 2048


class GravatarError(Exception):
	pass


def _fetch_gravatar(email: str) -> bytes | None:
	"""
	Returns the user's Gravatar re-encoded as a PNG, or None if they don't have one
	"""
	with requests.get(get_gravatar_url(email), stream=True, timeout=(5, 10)) as response:
		if response.status_code == 404:
			return None
		elif response.status_code != 200:
			raise GravatarError(f"Gravatar returned {response.status_code}")

		data = b""
		for chunk in response.iter_content(chunk_size=16 * 1024):
			data += chunk
			if len(data) > GRAVATAR_MAX_BYTES:
				raise GravatarError("Gravatar image is too large")

	# Re-encoding means only a valid image is ever served, whatever Gravatar returned
	try:
		with Image.open(io.BytesIO(data)) as source:
			if source.width > GRAVATAR_MAX_DIMENSION or source.height > GRAVATAR_MAX_DIMENSION:
				raise GravatarError(f"Gravatar image is too big: {source.width}x{source.height}")
			image = source.convert("RGBA")
	except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
		raise GravatarError(f"Gravatar returned an invalid image: {e}") from e

	out = io.BytesIO()
	image.save(out, format="PNG")
	return out.getvalue()


def _is_fresh(path: str) -> bool:
	try:
		return time.time() - os.path.getmtime(path) < GRAVATAR_CACHE_MAX_AGE
	except FileNotFoundError:
		return False


def _write_atomically(path: str, data: bytes):
	partial_path = f"{path}.{random_string(10)}.partial"
	with open(partial_path, "wb") as f:
		f.write(data)
	os.replace(partial_path, path)


def _redirect_to(url: str, max_age: int):
	res = redirect(url)
	res.headers["Cache-Control"] = f"public, max-age={max_age}"
	return res


@bp.route("/thumbnails/gravatar/<int:user_id>.png")
def gravatar(user_id: int):
	"""
	A proxy for Gravatar, so that browsers never see the hash of the user's email. See app.utils.gravatar.
	Without a Gravatar, it redirects to the user's other profile picture.
	"""
	user = User.query.get(user_id)
	if user is None:
		abort(404)

	fallback_url = user.get_fallback_profile_pic_url()
	if not user.use_gravatar or not user.email:
		return _redirect_to(fallback_url, 60 * 60)

	cache_dir = os.path.join(current_app.config["THUMBNAIL_DIR"], "gravatar")
	os.makedirs(cache_dir, exist_ok=True)

	# Keyed by the version, so changing email doesn't serve the old image
	image_path = os.path.join(cache_dir, f"{user.id}-{get_gravatar_version(user.email)}.png")
	missing_path = f"{image_path}.missing"

	if not _is_fresh(image_path):
		if _is_fresh(missing_path):
			return _redirect_to(fallback_url, 60 * 60)

		# Longer than the cache time, so a file that was just found to be fresh can't be pruned before it's sent
		prune_dir(cache_dir, 2 * GRAVATAR_CACHE_MAX_AGE)

		try:
			data = _fetch_gravatar(user.email)
		except (requests.RequestException, GravatarError) as e:
			print(f"Failed to fetch Gravatar for user {user.id}: {e}", file=sys.stderr)
			return _redirect_to(fallback_url, 5 * 60)

		if data is None:
			_write_atomically(missing_path, b"")
			return _redirect_to(fallback_url, 60 * 60)

		_write_atomically(image_path, data)

	res = send_file(image_path, mimetype="image/png")
	res.headers["Cache-Control"] = f"public, max-age={GRAVATAR_CACHE_MAX_AGE}"
	return res
