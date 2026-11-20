# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Any, ClassVar

from flask import render_template
from flask_babel import gettext, LazyString
from markupsafe import Markup

from app.models import DashboardWidget


class Widget:
	"""
	Base class for homepage widgets. Register subclasses in WIDGETS in app/blueprints/homepage/__init__.py.

	Templates live next to the widget's code. The homepage blueprint's template folder is its own package, so
	app/blueprints/homepage/widgets/foo/foo.html is the template "widgets/foo/foo.html".
	"""

	template: ClassVar[str]

	# Shown in the dashboard editor
	label: ClassVar[LazyString]

	# The DashboardWidget fields this widget uses, which the editor shows. One of "title", "query_string", "limit".
	fields: ClassVar[frozenset[str]] = frozenset({"title", "limit"})

	# Used when the widget's limit isn't set
	default_limit: ClassVar[int | None] = None

	def __init__(self, model: DashboardWidget):
		self.model = model

	def get_context(self) -> dict[str, Any]:
		"""Extra template variables. This is where the widget does its queries."""
		return {}

	def get_scripts(self) -> list[str]:
		"""URLs of scripts the page needs to include for this widget"""
		return []

	def get_limit(self) -> int | None:
		return self.model.limit or self.default_limit

	def get_title(self) -> str | None:
		# Titles are extracted for translation from /api/dashboards/ by utils/extract_translations.py
		return gettext(self.model.title) if self.model.title else None

	def render(self) -> Markup:
		context = {
			"widget": self.model,
			"title": self.get_title(),
			**self.get_context(),
		}
		return Markup(render_template(self.template, **context))  # noqa: S704 - templates are autoescaped
