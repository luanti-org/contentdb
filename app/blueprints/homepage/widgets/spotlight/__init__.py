# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from flask_babel import lazy_gettext
from sqlalchemy.orm import selectinload

from app.models import DashboardWidgetSlide, Package
from ..base import Widget


@dataclass
class Badge:
	title: str
	description: str


@dataclass
class Slide:
	"""One item in the carousel: a package or a custom slide"""

	title: str
	url: str
	image_url: Optional[str]
	description: Optional[str] = None
	author: Optional[str] = None
	label: Optional[str] = None
	warnings: list[Badge] = field(default_factory=list)
	tags: list[Badge] = field(default_factory=list)
	# (positive, neutral, negative) review counts, for packages
	review_summary: Optional[tuple[int, int, int]] = None

	@classmethod
	def from_package(cls, package: Package) -> "Slide":
		meta = package.get_translated(load_desc=False)
		tags = sorted(package.tags, key=lambda tag: tag.views, reverse=True)[:3]
		positive, neutral, negative = package.get_review_summary()
		return cls(
			title=meta["title"],
			url=package.get_url("packages.view"),
			image_url=package.get_cover_image_url(),
			description=meta["short_desc"],
			author=package.author.display_name,
			label=str(package.type.text),
			warnings=[Badge(**warning.get_translated()) for warning in package.content_warnings],
			tags=[Badge(**tag.get_translated()) for tag in tags],
			review_summary=(positive, neutral, negative))

	@classmethod
	def from_custom(cls, slide: DashboardWidgetSlide) -> "Slide":
		return cls(
			title=slide.title,
			url=slide.url,
			image_url=slide.get_image_url(),
			description=slide.description,
			label=slide.label)


class SpotlightWidget(Widget):
	"""
	A carousel of the widget's active custom slides, followed by packages from a package list query, such as
	"collection=ContentDB/spotlight&random". The limit applies to the packages.
	"""

	template = "widgets/spotlight/spotlight.html"
	label = lazy_gettext("Spotlight carousel")
	fields = frozenset({"query_string", "limit"})
	default_limit = 6
	has_slides = True

	def get_context(self) -> dict[str, Any]:
		now = datetime.datetime.utcnow()
		custom = self.model.slides.filter(DashboardWidgetSlide.active_filter(now)).all()

		packages = (self.query_builder.build_package_query()
			.options(
				selectinload(Package.tags),
				selectinload(Package.content_warnings),
				selectinload(Package.cover_image))
			.all())

		return {
			"slides": [Slide.from_custom(slide) for slide in custom] + [Slide.from_package(package) for package in packages],
		}
