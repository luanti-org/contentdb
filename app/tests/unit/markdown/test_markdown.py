# ContentDB
# Copyright (C) 2025 rubenwardy
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

from app.markdown import render_markdown

def test_linkify():
	assert render_markdown("hello readme.md https://readme.md") == "<p>hello readme.md <a href=\"https://readme.md\" rel=\"nofollow\">https://readme.md</a></p>\n"
