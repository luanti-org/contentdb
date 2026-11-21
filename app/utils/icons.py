# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os
import re
from functools import cache

ICON_RE = re.compile(r"^fa-[a-z0-9-]+$")

# Icons are shown with the "fas" class, so only the solid style counts. Brand icons (fab), such as fa-github, are
# also in the CSS, but render as nothing with fas.
SOLID_FONT = os.path.join(os.path.dirname(__file__), "..", "public", "static", "fa", "webfonts", "fa-solid-900.svg")


@cache
def get_icons() -> frozenset[str]:
	"""
	Class names of the solid icons in the bundled Font Awesome, such as "fa-dragon". It's version 5, so it doesn't
	have icons that were added or renamed in version 6.
	"""
	with open(SOLID_FONT, encoding="utf-8") as f:
		names = re.findall(r'glyph-name="([a-z0-9-]+)"', f.read())
	return frozenset(f"fa-{name}" for name in names)


def is_icon(name: str) -> bool:
	return ICON_RE.match(name) is not None and name in get_icons()
