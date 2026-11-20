# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Optional
from urllib.parse import parse_qsl, urlparse

from flask import abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext, lazy_gettext
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response
from wtforms import DateTimeLocalField, FieldList, FileField, Form, FormField, HiddenField, IntegerField, \
	StringField, SubmitField
from wtforms.validators import InputRequired, Length, NumberRange, Optional as OptionalValidator, ValidationError

from app.domain.DomainError import DomainError
from app.models import AuditSeverity, Dashboard, DashboardWidget, DashboardWidgetSlide, DashboardWidgetType, \
	Permission, db
from app.querybuilder import QueryBuilder
from app.uploads import upload_file
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

	slide_counts: dict[int, int] = {}
	if dashboard:
		slide_counts = dict(db.session.query(DashboardWidgetSlide.widget_id, db.func.count(DashboardWidgetSlide.id))
				.join(DashboardWidget)
				.filter(DashboardWidget.dashboard_id == dashboard.id)
				.group_by(DashboardWidgetSlide.widget_id)
				.all())

	def get_slides_link(sub: WidgetForm) -> Optional[tuple[str, int]]:
		if dashboard is None or not sub.id.data or not sub.id.data.isdigit():
			return None
		widget_id = int(sub.id.data)
		url = url_for("homepage.dashboard_slides", id=dashboard.id, widget_id=widget_id)
		return url, slide_counts.get(widget_id, 0)

	widgets = [(entry.form, get_widget_type(entry.form.type.data), get_slides_link(entry.form))
			for entry in form.widgets.entries]
	return render_template("homepage/editor/edit.html", dashboard=dashboard, form=form,
			widgets=widgets, widget_classes=WIDGETS, widget_templates=make_widget_templates())


def is_valid_slide_url(url: str) -> bool:
	"""An http(s) URL, or a path on this site"""
	# Browsers remove tabs and newlines from URLs, so "/\t/example.com" would become "//example.com"
	if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
		return False

	if url.startswith("/"):
		# //example.com is protocol-relative, so would go to another site
		return not url.startswith("//") and not url.startswith("/\\")

	parsed = urlparse(url)
	return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class SlideForm(Form):
	"""One custom slide in the slides form"""

	id = HiddenField()
	removed = HiddenField(default="0")
	order = HiddenField()

	title = StringField(lazy_gettext("Title"), [InputRequired(), Length(1, 100)])
	description = StringField(lazy_gettext("Description"), [OptionalValidator(), Length(0, 300)],
			filters=[nonempty_or_none])
	label = StringField(lazy_gettext("Label"), [OptionalValidator(), Length(0, 50)], filters=[nonempty_or_none])
	url = StringField(lazy_gettext("Link"), [InputRequired(), Length(1, 512)],
			filters=[lambda value: value.strip() if value else value])
	image = FileField(lazy_gettext("Image"))
	starts_at = DateTimeLocalField(lazy_gettext("Show from (UTC)"), [OptionalValidator()], format="%Y-%m-%dT%H:%M")
	ends_at = DateTimeLocalField(lazy_gettext("Show until (UTC)"), [OptionalValidator()], format="%Y-%m-%dT%H:%M")

	def validate(self, extra_validators=None):
		# Removed slides are deleted, so don't need to be valid
		if self.removed.data == "1":
			return True
		return super().validate(extra_validators)

	def validate_url(self, field):
		if not is_valid_slide_url(field.data):
			raise ValidationError(gettext("Must be an http(s) URL, or a path on this site starting with /"))

	def validate_image(self, field):
		if not self.id.data and not has_file(field.data):
			raise ValidationError(gettext("An image is required"))

	def validate_ends_at(self, field):
		if field.data and self.starts_at.data and field.data <= self.starts_at.data:
			raise ValidationError(gettext("Must be after the start"))


def has_file(data) -> bool:
	# Browsers post an empty file when none is chosen
	return data is not None and hasattr(data, "filename") and bool(data.filename)


class SlidesForm(FlaskForm):
	slides = FieldList(FormField(SlideForm), min_entries=0)
	submit = SubmitField(lazy_gettext("Save"))


def get_slides_initial_data(widget: DashboardWidget) -> dict:
	return {
		"slides": [
			{
				"id": str(slide.id),
				"removed": "0",
				"order": str(i),
				"title": slide.title,
				"description": slide.description,
				"label": slide.label,
				"url": slide.url,
				"starts_at": slide.starts_at,
				"ends_at": slide.ends_at,
			} for i, slide in enumerate(widget.slides.all())
		],
	}


def save_slides(widget: DashboardWidget, form: SlidesForm):
	"""Saves the slides, after uploading images. Raises DomainError if an image is invalid, before changing anything."""
	existing = {slide.id: slide for slide in widget.slides.all()}

	def get_order(entry) -> int:
		try:
			return int(entry.form.order.data)
		except (TypeError, ValueError):
			return len(form.slides.entries)

	entries = sorted(form.slides.entries, key=get_order)

	# Check ids and upload images first, so that an invalid image doesn't leave a half-saved list
	slides: list[tuple[SlideForm, Optional[DashboardWidgetSlide], Optional[str]]] = []
	for entry in entries:
		sub = entry.form
		slide: Optional[DashboardWidgetSlide] = None
		if sub.id.data:
			try:
				slide = existing.get(int(sub.id.data))
			except ValueError:
				abort(400)
			if slide is None:
				abort(400)

		image_path = None
		if sub.removed.data != "1" and has_file(sub.image.data):
			image_path, _ = upload_file(sub.image.data, "image", lazy_gettext("a PNG, JPEG, or WebP image file"))

		slides.append((sub, slide, image_path))

	order = 0
	for sub, slide, image_path in slides:
		if sub.removed.data == "1":
			if slide is not None:
				db.session.delete(slide)
			continue

		if slide is None:
			slide = DashboardWidgetSlide()
			slide.widget = widget
			db.session.add(slide)

		slide.title = sub.title.data
		slide.description = sub.description.data
		slide.label = sub.label.data
		slide.url = sub.url.data
		slide.starts_at = sub.starts_at.data
		slide.ends_at = sub.ends_at.data
		if image_path:
			slide.image_path = image_path
		slide.order = order
		order += 1


@bp.route("/dashboards/<int:id>/widgets/<int:widget_id>/slides/", methods=["GET", "POST"])
@login_required
def dashboard_slides(id: int, widget_id: int):
	dashboard = db.get_or_404(Dashboard, id)
	if not dashboard.check_perm(current_user, Permission.EDIT_DASHBOARD):
		abort(403)

	widget = db.get_or_404(DashboardWidget, widget_id)
	if widget.dashboard_id != dashboard.id or widget.type not in WIDGETS or not WIDGETS[widget.type].has_slides:
		abort(404)

	form = SlidesForm(data=get_slides_initial_data(widget) if request.method == "GET" else None)
	if form.validate_on_submit():
		try:
			save_slides(widget, form)
		except DomainError as e:
			db.session.rollback()
			flash(e.message, "danger")
		else:
			url = url_for("homepage.dashboard_slides", id=dashboard.id, widget_id=widget.id)
			add_audit_log(AuditSeverity.EDITOR, current_user, f"Edited slides in dashboard {dashboard.title}", url)
			db.session.commit()
			return redirect(url)

	existing = {slide.id: slide for slide in widget.slides.all()}

	def get_existing(sub: SlideForm) -> Optional[DashboardWidgetSlide]:
		return existing.get(int(sub.id.data)) if sub.id.data and sub.id.data.isdigit() else None

	slides = [(entry.form, get_existing(entry.form)) for entry in form.slides.entries]
	template = SlideForm(formdata=None, prefix="slides-__index__-", data={"removed": "0"})
	return render_template("homepage/editor/slides.html", dashboard=dashboard, widget=widget,
			widget_class=WIDGETS[widget.type], form=form, slides=slides, template=template)
