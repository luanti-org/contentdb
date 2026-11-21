# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2026 rubenwardy <rw@rubenwardy>

import flask
from flask import Blueprint, current_app, make_response, redirect, render_template, request
from flask_login import current_user
from markupsafe import Markup
from sqlalchemy.sql.expression import func

from app.models import Dashboard, DashboardWidget, DashboardWidgetType, Package, PackageState, db
from .widgets.base import Widget
from .widgets.categories import CategoriesWidget
from .widgets.reviews import ReviewsWidget
from .widgets.row import RowWidget
from .widgets.spotlight import SpotlightWidget
from .widgets.tags import TagsWidget

# The template folder is this package, so that widget templates can live next to their code
bp = Blueprint("homepage", __name__, template_folder=".")


# To add a widget type, add it to DashboardWidgetType, write a Widget subclass in widgets/, and register it here.
WIDGETS: dict[DashboardWidgetType, type[Widget]] = {
	DashboardWidgetType.SPOTLIGHT: SpotlightWidget,
	DashboardWidgetType.ROW: RowWidget,
	DashboardWidgetType.TAGS: TagsWidget,
	DashboardWidgetType.REVIEWS: ReviewsWidget,
	DashboardWidgetType.CATEGORIES: CategoriesWidget,
}


def render_widget(model: DashboardWidget, scripts: list[str]) -> Markup | None:
	"""
	Renders a widget, adding any scripts it needs to scripts.
	Returns None if it fails, so that one broken widget (such as a bad query) doesn't take down the whole page.
	"""
	try:
		widget = WIDGETS[model.type](model)
		html = widget.render()
		for script in widget.get_scripts():
			if script not in scripts:
				scripts.append(script)
		return html
	except Exception:
		current_app.logger.exception(f"Unable to render dashboard widget {model.id} ({model.type})")
		# The error may have been in the database, which aborts the transaction
		db.session.rollback()
		return None


@bp.route("/gamejam/")
def gamejam():
	return redirect("https://jam.luanti.org/")


@bp.route("/")
def home():
	# TODO: get correct dashboard
	dashboard = Dashboard.query.order_by(db.asc(Dashboard.id)).first()

	scripts: list[str] = []
	widgets = [render_widget(widget, scripts) for widget in dashboard.widgets.all()] if dashboard else []
	widgets = [html for html in widgets if html is not None]

	count = db.session.query(Package.id).filter(Package.state == PackageState.APPROVED).count()
	downloads_result = db.session.query(func.sum(Package.downloads)).one_or_none()
	downloads = 0 if not downloads_result or not downloads_result[0] else downloads_result[0]

	html = render_template("homepage/index.html", dashboard=dashboard, widgets=widgets, scripts=scripts, count=count,
			downloads=downloads)

	if not (flask.session or current_user.is_authenticated or request.headers.get("Authorization")):
		res = make_response(html)
		res.cache_control.public = True
		res.cache_control.private = None
		res.cache_control.max_age = 300
		res.cache_control.stale_if_error = 6*60*60
		res.cache_control.stale_while_revalidate = 30
		return res

	return html


from . import editor  # noqa: E402,F401 - registers the editor's routes on bp
