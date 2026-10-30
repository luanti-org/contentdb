# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import contextlib
import hashlib
import os
import tempfile
import shutil
from .misc import random_string

@contextlib.contextmanager
def get_temp_dir():
	temp = os.path.join(tempfile.gettempdir(), random_string(10))
	os.makedirs(temp, exist_ok=True)
	yield temp
	shutil.rmtree(temp, ignore_errors=True)


# Returns the SHA-256 of the file as lowercase hex
def sha256_file(path: str) -> str:
	with open(path, "rb") as f:
		return hashlib.file_digest(f, "sha256").hexdigest()
