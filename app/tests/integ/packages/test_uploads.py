# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Uploaded files: type checks, where they're stored, and serving them back.
"""

import io
import os

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import app
from app.domain.DomainError import DomainError
from app.uploads import upload_file, remove_png_hack


def make_image(fmt: str = "PNG", size: tuple[int, int] = (1280, 720)) -> bytes:
	buf = io.BytesIO()
	Image.new("RGB", size, (200, 100, 50)).save(buf, fmt)
	return buf.getvalue()


def make_file(data: bytes, filename: str) -> FileStorage:
	return FileStorage(stream=io.BytesIO(data), filename=filename)


def upload_dir_listing() -> set[str]:
	return set(os.listdir(app.config["UPLOAD_DIR"]))


@pytest.mark.parametrize("filename,fmt,ext", [
	("photo.png", "PNG", "png"),
	("photo.jpg", "JPEG", "jpg"),
	("photo.jpeg", "JPEG", "jpg"),
	("PHOTO.JPEG", "JPEG", "jpg"),
	("photo.PNG", "PNG", "png"),
	("photo.webp", "WEBP", "webp"),
])
def test_upload_image(client, filename, fmt, ext):
	data = make_image(fmt)

	url, local_path = upload_file(make_file(data, filename), "image", "an image")

	assert url.startswith("/uploads/")
	assert url.endswith("." + ext)
	assert os.path.dirname(local_path) == os.path.normpath(app.config["UPLOAD_DIR"])
	with open(local_path, "rb") as f:
		assert f.read() == data


def test_upload_name_is_random(client):
	"""
	The stored name must not come from the user's filename, which could contain a path.
	"""
	before = upload_dir_listing()

	url, local_path = upload_file(make_file(make_image(), "../../../etc/evil.png"), "image", "an image")

	assert "evil" not in url
	assert ".." not in url
	assert os.path.dirname(local_path) == os.path.normpath(app.config["UPLOAD_DIR"])
	assert upload_dir_listing() - before == {os.path.basename(local_path)}

	url2, _ = upload_file(make_file(make_image(), "../../../etc/evil.png"), "image", "an image")
	assert url2 != url


@pytest.mark.parametrize("file", [
	None,
	FileStorage(stream=io.BytesIO(b""), filename=""),
])
def test_upload_no_file(client, file):
	with pytest.raises(DomainError) as e:
		upload_file(file, "image", "an image")
	assert e.value.message == "Expected file"


@pytest.mark.parametrize("filename", ["photo", "photo.gif", "photo.svg", "photo.html", "photo.png.html", "png"])
def test_upload_wrong_extension(client, filename):
	before = upload_dir_listing()

	with pytest.raises(DomainError) as e:
		upload_file(make_file(make_image(), filename), "image", "an image")
	assert "Please upload an image" in str(e.value.message)
	assert upload_dir_listing() == before


@pytest.mark.parametrize("data", [
	b"<html><script>alert(1)</script></html>",
	b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
	b"GIF89a\x01\x00\x01\x00\x00\x00\x00;",
	b"PK\x05\x06" + b"\x00" * 18,
], ids=["html", "svg", "gif", "zip"])
def test_upload_rejects_non_images_with_image_extension(client, data):
	before = upload_dir_listing()

	with pytest.raises(DomainError) as e:
		upload_file(make_file(data, "photo.png"), "image", "an image")
	assert "isn't actually an image" in str(e.value.message)
	assert upload_dir_listing() == before


def test_upload_zip(client):
	data = b"PK\x05\x06" + b"\x00" * 18

	url, _ = upload_file(make_file(data, "mod.ZIP"), "zip", "a zip file")
	assert url.endswith(".zip")

	with pytest.raises(DomainError):
		upload_file(make_file(data, "mod.tar.gz"), "zip", "a zip file")
	with pytest.raises(DomainError):
		upload_file(make_file(make_image(), "photo.png"), "zip", "a zip file")


def test_serve_upload(client):
	data = make_image()
	url, _ = upload_file(make_file(data, "photo.png"), "image", "an image")

	rv = client.get(url)
	assert rv.status_code == 200
	assert rv.data == data


@pytest.mark.parametrize("path", [
	"/uploads/../../../etc/passwd",
	"/uploads/..%2F..%2F..%2Fetc%2Fpasswd",
	"/uploads/%2E%2E/%2E%2E/%2E%2E/etc/passwd",
	"/uploads//etc/passwd",
	"/uploads/%2Fetc%2Fpasswd",
])
def test_serve_upload_path_traversal(client, path):
	rv = client.get(path)
	assert rv.status_code in (404, 308)
	assert b"root:" not in rv.data


@pytest.mark.parametrize("path,expected", [
	("/uploads/abc.png", "/uploads/abc.png"),
	("/uploads/abc.jpg.png", "/uploads/abc.jpg"),
	("/uploads/abc.webp.png", "/uploads/abc.webp"),
	("/uploads/abc.jpg", "/uploads/abc.jpg"),
	("abc.png.jpg", "abc.png.jpg"),
])
def test_remove_png_hack(path, expected):
	assert remove_png_hack(path) == expected
