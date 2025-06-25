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

from app.utils.version import is_minetest_v510


def test_is_minetest_v510():
	assert not is_minetest_v510("Minetest/5.9.1 (Windows/10.0.22621 x86_64)")
	assert not is_minetest_v510("Minetest/")
	assert not is_minetest_v510("Minetest/5.9.1")

	assert is_minetest_v510("Minetest/5.10.0")
	assert is_minetest_v510("Minetest/5.10.1")
	assert is_minetest_v510("Minetest/5.11.0")
	assert is_minetest_v510("Minetest/5.10")

	assert not is_minetest_v510("Minetest/6.12")
