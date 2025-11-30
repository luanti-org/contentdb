# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from app.markdown import render_markdown

def test_linkify():
	assert render_markdown("hello readme.md https://readme.md") == "<p>hello readme.md <a href=\"https://readme.md\" rel=\"nofollow\">https://readme.md</a></p>\n"
