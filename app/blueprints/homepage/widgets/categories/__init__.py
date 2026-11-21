# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import math
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode

from flask import url_for
from flask_babel import lazy_gettext

from app.models import Package, PackageState, Tag, TagKind, Tags, db
from app.uploads import get_public_upload_url
from ..base import Widget


@dataclass
class CategoryTile:
	title: str
	description: Optional[str]
	url: str
	# Hue of the tile's gradient, 0-359
	hue: int
	# Picture of the category's top packages, made by a scheduled task, or None until then
	image_url: Optional[str]
	# Font Awesome icon class, such as "fa-dragon"
	icon: str


# For categories without an icon, set in the tag editor
DEFAULT_CATEGORY_ICON = "fa-gamepad"

# Hue of the first category, blue
FIRST_HUE = 210


def get_hues(count: int) -> list[int]:
	"""
	`count` different hues, spread evenly around the colour wheel, in an order where each is far from the one before
	it, so that neighbouring tiles never look alike
	"""
	if count <= 0:
		return []

	# Step through the evenly spaced hues by a stride that visits each once (coprime with count), about 0.4 of the way
	# round each time
	stride = max(1, round(count * 0.4))
	while math.gcd(stride, count) != 1:
		stride += 1

	return [(FIRST_HUE + (i * stride % count) * 360 // count) % 360 for i in range(count)]


class CategoriesWidget(Widget):
	"""
	A tile for each category tag that has packages, showing its title over a picture of its top packages and a
	coloured gradient, with its description on hover, linking to those packages.

	The query string is a base filter for every tile, such as "type=game": it decides which categories are shown and
	where they link, but not the picture, which is made per tag by app.tasks.collagetasks so that the homepage doesn't
	load any packages or thumbnails. Categories are shown in the order they were created, so the order the migration
	that adds them lists them in.
	"""

	template = "widgets/categories/categories.html"
	label = lazy_gettext("Categories")
	fields = frozenset({"title", "query_string"})

	def get_context(self) -> dict[str, Any]:
		qb = self.model.get_query_builder()
		query = db.session.query(Tag) \
			.select_from(Tag).join(Tags).join(Package) \
			.filter(Tag.kind == TagKind.CATEGORY, Package.state == PackageState.APPROVED) \
			.group_by(Tag.id) \
			.order_by(db.asc(Tag.id))
		query = qb.filter_package_query(query)

		# Hues come from every category, not just the ones shown, so a category has the same colour in every widget
		category_ids = [x[0] for x in db.session.query(Tag.id).filter(Tag.kind == TagKind.CATEGORY).order_by(db.asc(Tag.id))]
		hues = dict(zip(category_ids, get_hues(len(category_ids)), strict=True))

		base_args = parse_qsl(self.model.query_string or "", keep_blank_values=True)
		tiles = []
		for tag in query.all():
			translated = tag.get_translated()
			tiles.append(CategoryTile(
				title=translated["title"],
				description=translated["description"] or None,
				url=url_for("packages.list_all") + "?" + urlencode(base_args + [("tag", tag.name)]),
				hue=hues[tag.id],
				image_url=get_public_upload_url(tag.collage_path) if tag.collage_path else None,
				icon=tag.icon or DEFAULT_CATEGORY_ICON))

		return {
			"tiles": tiles,
		}
