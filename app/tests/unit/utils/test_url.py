# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from app.utils.url import clean_youtube_url


def test_clean_youtube_url():
	assert clean_youtube_url(
		"https://www.youtube.com/watch?v=AABBCC") == "https://www.youtube.com/watch?v=AABBCC"
	assert clean_youtube_url(
		"https://www.youtube.com/watch?v=boGcB4H5-WA&other=1") == "https://www.youtube.com/watch?v=boGcB4H5-WA"
	assert clean_youtube_url("https://www.youtube.com/watch?kk=boGcB4H5-WA&other=1") is None
	assert clean_youtube_url("https://www.bob.com/watch?v=AABBCC") is None

	assert clean_youtube_url("https://youtu.be/boGcB4H5-WA") == "https://www.youtube.com/watch?v=boGcB4H5-WA"
	assert clean_youtube_url("https://youtu.be/boGcB4H5-WA?this=1") == "https://www.youtube.com/watch?v=boGcB4H5-WA"
