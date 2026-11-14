# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import re


def inline_code(text: str) -> str:
	"""
	Formats untrusted text as Discord inline code, so that it can't add markdown, masked links, or embeds.

	Backticks can't be escaped inside inline code, so they're replaced, as are newlines and control characters.
	"""
	text = re.sub(r"[\x00-\x1f\x7f]", " ", text.replace("`", "'"))
	return f"`{text}`"
