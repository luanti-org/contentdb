# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional
from zipfile import ZipFile

import imagehash
import numpy
from PIL import Image

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tga", ".bmp")

DEFAULT_THRESHOLD = 8
MAX_MATCHES_PER_IMAGE = 5


@dataclass
class PossibleMatch:
	# Path to content inside the zip file
	content_path: str

	# Name of the dataset
	match_dataset: str

	# Unique path for copyrighted material in dataset
	match_path: str

	# Confidence of match
	confidence: float

	# Hash of the content_path image, so callers can dedupe/persist without re-hashing
	content_phash: str
	content_dhash: str


@dataclass
class Hash:
	phash: str
	dhash: str


@dataclass
class DatasetEntry:
	dataset: str
	path: str
	width: int
	height: int
	hashes: List[Hash]


def hash_to_int(h) -> int:
	return int.from_bytes(numpy.packbits(h.hash.flatten()).tobytes(), "big")


def hamming(a: int, b: int) -> int:
	return (a ^ b).bit_count()


# Weighted toward whichever of phash/dhash agrees more.
def combined_distance(phash_dist: int, dhash_dist: int) -> float:
	smaller, larger = (phash_dist, dhash_dist) if phash_dist <= dhash_dist else (dhash_dist, phash_dist)
	return (2 * smaller + larger) / 3


def best_distance(phash: int, dhash: int, entry: DatasetEntry) -> Optional[float]:
	best = None
	for h in entry.hashes:
		dist = combined_distance(hamming(phash, int(h.phash, 16)), hamming(dhash, int(h.dhash, 16)))
		if best is None or dist < best:
			best = dist
	return best


def find_matches(
		zip_file_path: str, entries: List[DatasetEntry],
		threshold: float = DEFAULT_THRESHOLD, max_matches: int = MAX_MATCHES_PER_IMAGE
) -> List[PossibleMatch]:
	results = []
	with ZipFile(zip_file_path, 'r') as zf:
		image_names = [name for name in zf.namelist() if name.lower().endswith(IMAGE_EXTS)]
		for name in image_names:
			with zf.open(name) as f:
				try:
					img = Image.open(BytesIO(f.read())).convert("RGBA")
				except Exception:
					continue

			phash_obj = imagehash.phash(img, hash_size=16)
			dhash_obj = imagehash.dhash(img, hash_size=16)
			phash = hash_to_int(phash_obj)
			dhash = hash_to_int(dhash_obj)

			# TODO: skip solid/flat-color images here

			candidates = []
			for entry in entries:
				dist = best_distance(phash, dhash, entry)
				if dist is not None and dist <= threshold:
					candidates.append((dist, entry))
			candidates.sort(key=lambda cand: cand[0])

			for dist, entry in candidates[:max_matches]:
				results.append(PossibleMatch(
					content_path=name,
					match_dataset=entry.dataset,
					match_path=entry.path,
					confidence=dist,
					content_phash=str(phash_obj),
					content_dhash=str(dhash_obj),
				))

	return results
