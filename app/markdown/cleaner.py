# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from functools import partial
from bleach import Cleaner
from bleach.linkifier import LinkifyFilter, DEFAULT_CALLBACKS


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
	"sup",
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


def allow_a(_tag, name, value):
	return name in ["href", "title", "data-username"] or (name == "class" and value == "header-anchor")


ALLOWED_ATTRIBUTES = {
	"h1": ["id"],
	"h2": ["id"],
	"h3": ["id"],
	"h4": ["id"],
	"a": allow_a,
	"img": ["src", "title", "alt"],
	"code": allow_class,
	"div": allow_class,
	"span": allow_class,
	"table": ["id"],
}

ALLOWED_PROTOCOLS = {"http", "https", "mailto"}


def linker_callback(attrs, new=False):
	if new:
		text = attrs.get("_text")
		if not (text.startswith("http://") or text.startswith("https://")):
			return None

	return attrs


def clean_html(html: str):
	cleaner = Cleaner(
		tags=ALLOWED_TAGS,
		attributes=ALLOWED_ATTRIBUTES,
		protocols=ALLOWED_PROTOCOLS,
		filters=[partial(LinkifyFilter,
				callbacks=[linker_callback] + DEFAULT_CALLBACKS,
				skip_tags={"pre", "code"})])
	return cleaner.clean(html)
