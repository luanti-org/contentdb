# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Optional
import secrets

def truncate_string(value: Optional[str], max_length: int) -> Optional[str]:
	if value is None:
		return None

	if len(value) <= max_length:
		return value

	return value[:max_length - 1] + "…"


YESES = ["yes", "true", "1", "on"]


def is_yes(val: Optional[str]) -> bool:
	return val and val.lower() in YESES


def is_no(val: Optional[str]) -> bool:
	return val and not is_yes(val)


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
