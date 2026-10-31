# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Optional
import hashlib
import secrets

def truncate_string(value: Optional[str], max_length: int) -> Optional[str]:
	if value is None:
		return None

	if len(value) <= max_length:
		return value

	return value[:max_length - 1] + "…"


YESES = ["yes", "true", "1", "on"]


def is_yes(val: Optional[str]) -> bool:
	return bool(val and val.lower() in YESES)


def is_no(val: Optional[str]) -> bool:
	return bool(val) and not is_yes(val)


def nonempty_or_none(str: Optional[str]) -> Optional[str]:
	if str is None or str == "":
		return None

	return str


def normalize_line_endings(value: Optional[str]) -> Optional[str]:
	if value is None:
		return None

	return value.replace("\r\n", "\n")


def random_string(n):
	return secrets.token_hex(int(n / 2))


# Only for random tokens, use a slow hash for passwords
def hash_token(token: str) -> str:
	return hashlib.sha256(token.encode("utf-8")).hexdigest()


def format_file_size(bytes: int) -> str:
	size = bytes / 1024
	if size > 1024:
		return f"{round(size / 1024, 1)} MB"
	else:
		return f"{round(size)} KB"
