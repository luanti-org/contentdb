# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from dataclasses import dataclass
from typing import List
from zipfile import ZipFile
import imagehash


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


def find_matches(zip_file_path: str, entries: List[DatasetEntry]) -> List[PossibleMatch]:
	with ZipFile(zip_file_path, 'r') as zf:
		lua_files = [name for name in zf.namelist() if name.endswith(".png")]
		for lua_file in lua_files:
			with zf.open(lua_file) as f:
				pass

	return []
