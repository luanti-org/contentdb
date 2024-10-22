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


def is_minetest_v510(user_agent: str) -> bool:
	parts = user_agent.split(" ")
	version = parts[0].split("/")[1]
	try:
		digits = list(map(lambda x: int(x), version.split(".")))
	except ValueError:
		return False

	if len(digits) < 2:
		return False

	return digits[0] == 5 and digits[1] >= 10
