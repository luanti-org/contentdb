# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import joinedload, load_only, subqueryload
from sqlalchemy.sql.expression import func

from app.models import Collection, License, Package, PackageState, User
from ..base import Widget


class SpotlightWidget(Widget):
	"""A carousel of random packages from the ContentDB/spotlight collection"""

	template = "widgets/spotlight/spotlight.html"

	def get_context(self) -> dict[str, Any]:
		packages = (Package.query
			.filter(
				Package.state == PackageState.APPROVED,
				Package.collections.any(and_(Collection.name == "spotlight", Collection.author.has(username="ContentDB"))))
			.options(
				load_only(Package.name, Package.title, Package.type, Package.short_desc, Package.state,
						Package.cover_image_id, raiseload=True),
				subqueryload(Package.main_screenshot),
				joinedload(Package.tags),
				joinedload(Package.content_warnings),
				joinedload(Package.author).load_only(User.username, User.display_name, raiseload=True),
				subqueryload(Package.cover_image),
				joinedload(Package.license).load_only(License.name, License.is_foss, raiseload=True),
				joinedload(Package.media_license).load_only(License.name, License.is_foss, raiseload=True))
			.order_by(func.random())
			.limit(self.model.limit or 6)
			.all())

		return {
			"packages": packages,
		}
