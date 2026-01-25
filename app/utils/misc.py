# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

def truncate_string(value: str, max_length: int) -> str:
	if len(value) <= max_length:
		return value

	return value[:max_length - 1] + "…"
