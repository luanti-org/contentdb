# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Optional
from urllib.parse import parse_qsl

from flask import abort, redirect, render_template, request, url_for
from flask_babel import gettext, lazy_gettext
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response
from wtforms import FieldList, Form, FormField, HiddenField, IntegerField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, NumberRange, Optional as OptionalValidator, ValidationError

from app.models import AuditSeverity, Dashboard, DashboardWidget, DashboardWidgetType, Permission, db
from app.querybuilder import QueryBuilder
from app.utils.misc import nonempty_or_none
from app.utils.models import add_audit_log
from . import bp, WIDGETS


def normalize_query_string(value: Optional[str]) -> Optional[str]:
	"""Accepts either a query string or a package list URL, such as /packages/?type=game&sort=score"""
	if value is None:
		return None

	value = value.strip()
	if "?" in value:
		value = value.split("?", 1)[1]

	return value or None


def get_query_error(query_string: str) -> Optional[str]:
	"""Returns why the package list query is invalid, or None if it's valid"""
	try:
		args = MultiDict(parse_qsl(query_string, keep_blank_values=True))
		# Builds without running it, which is enough to check every argument
		QueryBuilder(args, emit_http_errors=True).build_package_query()
	except HTTPException as e:
		# QueryBuilder aborts with a plain text response describing the problem
		if isinstance(e.response, Response):
			return e.response.get_data(as_text=True)
		return e.description or str(e)

	return None


def get_widget_type(name: Optional[str]) -> Optional[DashboardWidgetType]:
	widget_type = DashboardWidgetType.get(name) if name else None
	return widget_type if widget_type in WIDGETS else None


class WidgetForm(Form):
	"""One widget in the dashboard form. Only the fields in the widget's Widget.fields are shown and saved."""

	id = HiddenField()
	type = HiddenField(validators=[InputRequired()])
	removed = HiddenField(default="0")
	order = HiddenField()

	title = StringField(lazy_gettext("Title"), [OptionalValidator(), Length(0, 100)], filters=[nonempty_or_none])
	query_string = StringField(lazy_gettext("Package list query"), [OptionalValidator(), Length(0, 512)],
			filters=[normalize_query_string])
	limit = IntegerField(lazy_gettext("Maximum items"), [OptionalValidator(), NumberRange(1, 50)])

	def validate_type(self, field):
		if get_widget_type(field.data) is None:
			raise ValidationError(gettext("Unknown widget type"))

	def validate_query_string(self, field):
		widget_type = get_widget_type(self.type.data)
		if self.removed.data == "1" or widget_type is None or "query_string" not in WIDGETS[widget_type].fields:
			return

		if field.data:
			error = get_query_error(field.data)
			if error:
				raise ValidationError(error)


class DashboardForm(FlaskForm):
	title = StringField(lazy_gettext("Title"), [InputRequired(), Length(1, 100)])
	widgets = FieldList(FormField(WidgetForm), min_entries=0)
	submit = SubmitField(lazy_gettext("Save"))


def get_initial_data(dashboard: Dashboard) -> dict:
	return {
		"title": dashboard.title,
		"widgets": [
			{
				"id": str(widget.id),
				"type": widget.type.name,
				"removed": "0",
				"order": str(i),
				"title": widget.title,
				"query_string": widget.query_string,
				"limit": widget.limit,
			} for i, widget in enumerate(dashboard.widgets.all())
		],
	}


def save_widgets(dashboard: Dashboard, form: DashboardForm):
	existing = {widget.id: widget for widget in dashboard.widgets.all()}

	def get_order(entry) -> int:
		try:
			return int(entry.form.order.data)
		except (TypeError, ValueError):
			return len(form.widgets.entries)

	entries = sorted(form.widgets.entries, key=get_order)

	order = 0
	for entry in entries:
		sub = entry.form
		widget_type = get_widget_type(sub.type.data)
		assert widget_type is not None  # checked by WidgetForm.validate_type

		widget: Optional[DashboardWidget] = None
		if sub.id.data:
			try:
				widget = existing.get(int(sub.id.data))
			except ValueError:
				abort(400)
			if widget is None or widget.type != widget_type:
				abort(400)

		if sub.removed.data == "1":
			if widget is not None:
				db.session.delete(widget)
			continue

		if widget is None:
			widget = DashboardWidget()
			widget.dashboard = dashboard
			widget.type = widget_type
			db.session.add(widget)

		fields = WIDGETS[widget_type].fields
		widget.title = sub.title.data if "title" in fields else None
		widget.query_string = sub.query_string.data if "query_string" in fields else None
		widget.limit = sub.limit.data if "limit" in fields else None
		widget.order = order
		order += 1


def make_widget_templates() -> list[tuple[DashboardWidgetType, WidgetForm]]:
	"""Blank widget forms, which the editor's JavaScript copies to add widgets. __index__ is replaced by the index."""
	return [
		(widget_type, WidgetForm(formdata=None, prefix="widgets-__index__-", data={"type": widget_type.name, "removed": "0"}))
		for widget_type in WIDGETS
	]


@bp.route("/dashboards/")
@login_required
def dashboard_list():
	if not Permission.EDIT_DASHBOARD.check(current_user):
		abort(403)

	dashboards = Dashboard.query.order_by(db.asc(Dashboard.id)).all()
	return render_template("homepage/editor/list.html", dashboards=dashboards)


@bp.route("/dashboards/new/", methods=["GET", "POST"])
@bp.route("/dashboards/<int:id>/edit/", methods=["GET", "POST"])
@login_required
def dashboard_edit(id: Optional[int] = None):
	dashboard: Optional[Dashboard] = None
	if id is not None:
		dashboard = db.get_or_404(Dashboard, id)
		if not dashboard.check_perm(current_user, Permission.EDIT_DASHBOARD):
			abort(403)
	elif not Permission.EDIT_DASHBOARD.check(current_user):
		abort(403)

	form = DashboardForm(data=get_initial_data(dashboard) if dashboard and request.method == "GET" else None)
	if form.validate_on_submit():
		is_new = dashboard is None
		if dashboard is None:
			dashboard = Dashboard()
			db.session.add(dashboard)

		dashboard.title = form.title.data
		save_widgets(dashboard, form)
		db.session.flush()

		url = url_for("homepage.dashboard_edit", id=dashboard.id)
		add_audit_log(AuditSeverity.EDITOR, current_user,
				f"{'Created' if is_new else 'Edited'} dashboard {dashboard.title}", url)
		db.session.commit()
		return redirect(url)

	widgets = [(entry.form, get_widget_type(entry.form.type.data)) for entry in form.widgets.entries]
	return render_template("homepage/editor/edit.html", dashboard=dashboard, form=form,
			widgets=widgets, widget_classes=WIDGETS, widget_templates=make_widget_templates())
