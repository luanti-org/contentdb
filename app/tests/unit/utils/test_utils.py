# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import user_agents

from app.utils import make_valid_username


def test_make_valid_username():
	assert make_valid_username("rubenwardy") == "rubenwardy"
	assert make_valid_username("Test123._-") == "Test123._-"
	assert make_valid_username("Foo Bar") == "Foo_Bar"
	assert make_valid_username("François") == "Fran_ois"


def test_web_is_not_bot():
	assert not user_agents.parse("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0").is_bot
	assert not user_agents.parse("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
			"Chrome/125.0.0.0 Safari/537.36").is_bot


def test_luanti_is_not_bot():
	assert not user_agents.parse("Minetest/5.5.1 (Linux/4.14.193+-ab49821 aarch64)").is_bot
	assert not user_agents.parse("Luanti/5.12.0 (Linux/4.14.193+-ab49821 aarch64)").is_bot


def test_crawlers_are_bots():
	assert user_agents.parse("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, "
			"like Gecko) Chrome/W.X.Y.Z Mobile Safari/537.36 (compatible; Googlebot/2.1; "
			"+http://www.google.com/bot.html)").is_bot
