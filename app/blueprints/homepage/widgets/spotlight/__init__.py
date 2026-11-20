# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Any

from flask_babel import lazy_gettext
from sqlalchemy.orm import selectinload

from app.models import Package
from ..base import Widget


class SpotlightWidget(Widget):
	"""A carousel of packages from a package list query, such as "collection=ContentDB/spotlight&random" """

	template = "widgets/spotlight/spotlight.html"
	label = lazy_gettext("Carousel")
	fields = frozenset({"query_string", "limit"})
	default_limit = 6

	def get_context(self) -> dict[str, Any]:
		packages = (self.query_builder.build_package_query()
			.options(
				selectinload(Package.tags),
				selectinload(Package.content_warnings),
				selectinload(Package.cover_image))
			.all())

		return {
			"packages": packages,
		}
