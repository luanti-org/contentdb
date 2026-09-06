# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

import os
import tempfile
from io import BytesIO
from zipfile import ZipFile

from PIL import Image

from app.tasks.hashcheck import (
	DatasetEntry,
	Hash,
	best_distance,
	combined_distance,
	find_matches_in_dir,
	find_matches_in_zip,
	hamming,
	hash_to_int,
	process_image,
)

import imagehash


def make_image(color=(200, 50, 80, 255), size=(32, 32)) -> Image.Image:
	return Image.new("RGBA", size, color)


def image_hashes(img: Image.Image):
	"""Compute the same phash/dhash pair that process_image() would produce."""
	phash_obj = imagehash.phash(img, hash_size=16)
	dhash_obj = imagehash.dhash(img, hash_size=16)
	return hash_to_int(phash_obj), hash_to_int(dhash_obj)


def flip_hex(value: int, num_bits: int) -> str:
	"""Flip the lowest num_bits bits of value, returning a 64-char hex string."""
	mask = (1 << num_bits) - 1 if num_bits > 0 else 0
	return format(value ^ mask, "064x")


def make_entry(dataset: str, path: str, phash_int: int, dhash_int: int,
		phash_flip_bits: int = 0, dhash_flip_bits: int = 0) -> DatasetEntry:
	return DatasetEntry(
		dataset=dataset,
		path=path,
		width=32,
		height=32,
		hashes=[Hash(
			phash=flip_hex(phash_int, phash_flip_bits),
			dhash=flip_hex(dhash_int, dhash_flip_bits),
		)],
	)


def test_hash_to_int_matches_hex_string_representation():
	# best_distance() parses stored hashes back via int(h.phash, 16),
	# so hash_to_int() must agree with the hex string produced by str()
	img = make_image()
	phash_obj = imagehash.phash(img, hash_size=16)

	assert hash_to_int(phash_obj) == int(str(phash_obj), 16)


def test_hamming():
	assert hamming(0, 0) == 0
	assert hamming(0b1010, 0b1010) == 0
	assert hamming(0, 0xFF) == 8
	assert hamming(0b1010, 0b0010) == 1


def test_combined_distance_weights_towards_smaller():
	assert combined_distance(2, 10) == (2 * 2 + 10) / 3
	assert combined_distance(10, 2) == (2 * 2 + 10) / 3
	assert combined_distance(0, 0) == 0


def test_best_distance_picks_closest_hash_in_entry():
	img = make_image()
	phash, dhash = image_hashes(img)

	entry = DatasetEntry(
		dataset="ds", path="far-and-close", width=32, height=32,
		hashes=[
			Hash(phash=flip_hex(phash, 256), dhash=flip_hex(dhash, 256)),
			Hash(phash=flip_hex(phash, 0), dhash=flip_hex(dhash, 0)),
		],
	)

	assert best_distance(phash, dhash, entry) == 0


def test_process_image_exact_match():
	img = make_image()
	phash, dhash = image_hashes(img)
	entry = make_entry("ds", "match.png", phash, dhash)

	results = process_image("content.png", img, [entry], threshold=8, max_matches=5)

	assert len(results) == 1
	match = results[0]
	assert match.content_path == "content.png"
	assert match.match_dataset == "ds"
	assert match.match_path == "match.png"
	assert match.confidence == 0

	assert match.content_phash == str(imagehash.phash(img, hash_size=16))
	assert match.content_dhash == str(imagehash.dhash(img, hash_size=16))

	roundtripped = Image.open(BytesIO(match.content_data))
	assert roundtripped.size == img.size


def test_process_image_excludes_beyond_threshold():
	img = make_image()
	phash, dhash = image_hashes(img)
	far_entry = make_entry("ds", "far.png", phash, dhash, phash_flip_bits=256, dhash_flip_bits=256)

	results = process_image("content.png", img, [far_entry], threshold=8, max_matches=5)

	assert results == []


def test_process_image_respects_threshold_boundary():
	img = make_image()
	phash, dhash = image_hashes(img)
	# dhash unchanged, phash off by 3 bits -> combined_distance == (2*0 + 3) / 3 == 1.0
	entry = make_entry("ds", "close.png", phash, dhash, phash_flip_bits=3)

	assert process_image("c.png", img, [entry], threshold=0.5, max_matches=5) == []

	results = process_image("c.png", img, [entry], threshold=1.0, max_matches=5)
	assert len(results) == 1
	assert results[0].confidence == 1.0


def test_process_image_sorts_and_truncates_to_max_matches():
	img = make_image()
	phash, dhash = image_hashes(img)

	exact = make_entry("ds", "exact.png", phash, dhash)
	close = make_entry("ds", "close.png", phash, dhash, phash_flip_bits=3)
	far = make_entry("ds", "far.png", phash, dhash, phash_flip_bits=6)

	# Deliberately out of order to check sorting
	results = process_image("c.png", img, [close, far, exact], threshold=100, max_matches=2)

	assert len(results) == 2
	assert [r.match_path for r in results] == ["exact.png", "close.png"]
	assert results[0].confidence <= results[1].confidence


def test_find_matches_in_zip_skips_non_images_and_unreadable_files():
	img = make_image()
	phash, dhash = image_hashes(img)
	entry = make_entry("ds", "match.png", phash, dhash)

	buffer = BytesIO()
	img.save(buffer, format="PNG")

	def build_zip(path):
		with ZipFile(path, "w") as zf:
			zf.writestr("textures/foo.png", buffer.getvalue())
			zf.writestr("readme.txt", "not an image")
			zf.writestr("textures/bad.png", b"not actually a png")

	with tempfile.TemporaryDirectory() as tmp:
		zip_path = os.path.join(tmp, "pkg.zip")
		build_zip(zip_path)

		results = find_matches_in_zip(zip_path, [entry], threshold=8, max_matches=5)

	assert len(results) == 1
	assert results[0].content_path == "textures/foo.png"


def test_find_matches_in_dir_finds_nested_case_insensitive_images():
	img = make_image()
	phash, dhash = image_hashes(img)
	entry = make_entry("ds", "match.png", phash, dhash)

	with tempfile.TemporaryDirectory() as tmp:
		nested_dir = os.path.join(tmp, "sub")
		os.makedirs(nested_dir)
		img.save(os.path.join(nested_dir, "foo.PNG"))
		with open(os.path.join(tmp, "readme.txt"), "w") as f:
			f.write("not an image")

		results = find_matches_in_dir(tmp, [entry], threshold=8, max_matches=5)

	assert len(results) == 1
	assert results[0].content_path == os.path.join("sub", "foo.PNG")
