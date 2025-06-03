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

from bleach import Cleaner


# Based on
# https://github.com/Wenzil/mdx_bleach/blob/master/mdx_bleach/whitelist.py
#
# License: MIT

ALLOWED_TAGS = {
	"h1", "h2", "h3", "h4", "h5", "h6", "hr",
	"ul", "ol", "li",
	"p",
	"br",
	"pre",
	"code",
	"blockquote",
	"strong",
	"em",
	"a",
	"img",
	"table", "thead", "tbody", "tr", "th", "td",
	"div", "span", "del", "s",
	"details",
	"summary",
}

ALLOWED_CSS = [
	"highlight", "codehilite",
	"hll", "c", "err", "g", "k", "l", "n", "o", "x", "p", "ch", "cm", "cp", "cpf", "c1", "cs",
	"gd", "ge", "gr", "gh", "gi", "go", "gp", "gs", "gu", "gt", "kc", "kd", "kn", "kp", "kr",
	"kt", "ld", "m", "s", "na", "nb", "nc", "no", "nd", "ni", "ne", "nf", "nl", "nn", "nx",
	"py", "nt", "nv", "ow", "w", "mb", "mf", "mh", "mi", "mo", "sa", "sb", "sc", "dl", "sd",
	"s2", "se", "sh", "si", "sx", "sr", "s1", "ss", "bp", "fm", "vc", "vg", "vi", "vm", "il",
]


def allow_class(_tag, name, value):
	return name == "class" and value in ALLOWED_CSS


ALLOWED_ATTRIBUTES = {
	"h1": ["id"],
	"h2": ["id"],
	"h3": ["id"],
	"h4": ["id"],
	"a": ["href", "title", "data-username"],
	"img": ["src", "title", "alt"],
	"code": allow_class,
	"div": allow_class,
	"span": allow_class,
	"table": ["id"],
}

ALLOWED_PROTOCOLS = {"http", "https", "mailto"}


def clean_html(html: str):
	cleaner = Cleaner(
		tags=ALLOWED_TAGS,
		attributes=ALLOWED_ATTRIBUTES,
		protocols=ALLOWED_PROTOCOLS)
	return cleaner.clean(html)
