# ContentDB
# Copyright (C) rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
