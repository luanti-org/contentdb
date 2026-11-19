# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from functools import cached_property
from typing import Any

from app.querybuilder import QueryBuilder
from ..base import Widget


class RowWidget(Widget):
	"""A row of packages from a package list query, like /packages/"""

	template = "widgets/row/row.html"

	@cached_property
	def query_builder(self) -> QueryBuilder:
		qb = self.model.get_query_builder()
		qb.limit = self.model.limit
		return qb

	def get_title(self) -> str | None:
		return super().get_title() or str(self.query_builder.title)

	def get_context(self) -> dict[str, Any]:
		return {
			"packages": self.query_builder.build_package_query().all(),
			"see_more_url": self.model.get_see_more_url(),
		}
