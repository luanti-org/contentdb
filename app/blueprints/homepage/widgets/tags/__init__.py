# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Any

from flask_babel import lazy_gettext
from sqlalchemy.sql.expression import func

from app.models import Package, PackageState, Tag, Tags, db
from ..base import Widget


class TagsWidget(Widget):
	"""Buttons for every tag in use, with package counts"""

	template = "widgets/tags/tags.html"
	label = lazy_gettext("Tags")
	fields = frozenset({"title"})

	def get_context(self) -> dict[str, Any]:
		tags = (db.session.query(func.count(Tags.c.tag_id), Tag)
			.select_from(Tag).outerjoin(Tags).join(Package)
			.filter(Package.state == PackageState.APPROVED)
			.group_by(Tag.id)
			.order_by(db.asc(Tag.title))
			.all())

		return {
			"tags": tags,
		}
