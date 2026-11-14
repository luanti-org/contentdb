# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Any
from unittest.mock import MagicMock

import pytest

from app import app
from app.tasks import webhooktasks
from app.utils.discord import inline_code


@pytest.mark.parametrize("text, expected", [
	("plain", "`plain`"),
	("@everyone [click](https://evil.example)", "`@everyone [click](https://evil.example)`"),
	# A backtick would end the inline code early
	("a`[click](https://evil.example)`b", "`a'[click](https://evil.example)'b`"),
	# A newline would let the rest start a new markdown line, such as a heading
	("a\n# Heading\r\x00\x7f", "`a # Heading   `"),
])
def test_inline_code(text, expected):
	assert inline_code(text) == expected


def test_webhook_disables_mentions(monkeypatch):
	posted: list[dict[str, Any]] = []

	def post(url, json, **kwargs):
		posted.append({"url": url, "json": json})
		return MagicMock(ok=True)

	monkeypatch.setitem(app.config, "DISCORD_WEBHOOK_QUEUE", "https://discord.example/queue")
	monkeypatch.setattr(webhooktasks.requests, "post", post)

	webhooktasks.post_discord_webhook(None, "@everyone <@&123> look", True)

	[call] = posted
	assert call["url"] == "https://discord.example/queue"
	assert call["json"]["content"] == "@everyone <@&123> look"
	assert call["json"]["allowed_mentions"] == {"parse": []}
