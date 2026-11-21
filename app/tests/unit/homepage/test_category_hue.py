# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from app.blueprints.homepage.widgets.categories import get_tag_hue


def test_tag_hue_is_stable():
	# zlib.crc32 is the same in every process, unlike hash(), which is randomised for strings
	assert get_tag_hue("category_puzzle") == get_tag_hue("category_puzzle")
	assert all(0 <= get_tag_hue(f"tag{i}") < 360 for i in range(50))
	assert len({get_tag_hue(f"tag{i}") for i in range(50)}) > 10
