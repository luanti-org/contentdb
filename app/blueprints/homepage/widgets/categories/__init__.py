# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode

from flask import url_for
from flask_babel import lazy_gettext

from app.models import Package, PackageState, Tag, TagKind, Tags, db
from ..base import Widget


@dataclass
class CategoryTile:
	title: str
	description: Optional[str]
	url: str


class CategoriesWidget(Widget):
	"""
	A tile for each category tag that has packages, showing its title (and its description on hover), linking to those
	packages. The query string is a base
	filter for every tile, such as "type=game". Categories are shown in the order they were created, so the order the
	migration that adds them lists them in.
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

		base_args = parse_qsl(self.model.query_string or "", keep_blank_values=True)
		tiles = []
		for tag in query.all():
			translated = tag.get_translated()
			tiles.append(CategoryTile(
				title=translated["title"],
				description=translated["description"] or None,
				url=url_for("packages.list_all") + "?" + urlencode(base_args + [("tag", tag.name)])))

		return {
			"tiles": tiles,
		}
