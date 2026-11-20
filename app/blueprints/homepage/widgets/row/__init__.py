# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Any

from flask_babel import lazy_gettext

from ..base import Widget


class RowWidget(Widget):
	"""A row of packages from a package list query, like /packages/"""

	template = "widgets/row/row.html"
	label = lazy_gettext("Package row")
	fields = frozenset({"title", "query_string", "limit"})
	default_limit = 8

	def get_title(self) -> str | None:
		return super().get_title() or str(self.query_builder.title)

	def get_context(self) -> dict[str, Any]:
		return {
			"packages": self.query_builder.build_package_query(for_tiles=True).all(),
			"see_more_url": self.model.get_see_more_url(),
		}
