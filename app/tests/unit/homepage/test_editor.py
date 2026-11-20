# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest

from app import app
from app.blueprints.homepage.editor import get_query_error, make_widget_templates, normalize_query_string


@pytest.mark.parametrize("value,expected", [
	(None, None),
	("", None),
	("  ", None),
	("type=game&sort=score", "type=game&sort=score"),
	(" type=game ", "type=game"),
	("?type=game", "type=game"),
	("/packages/?type=game&sort=score", "type=game&sort=score"),
	("https://content.luanti.org/packages/?type=mod", "type=mod"),
	("https://content.luanti.org/packages/?", None),
])
def test_normalize_query_string(value, expected):
	assert normalize_query_string(value) == expected


@pytest.mark.parametrize("query_string", [
	"",
	"type=game&sort=score&order=desc",
	"sort=last_release",
	"type=mod&type=txp&random",
])
def test_get_query_error_valid(query_string):
	with app.test_request_context("/dashboards/1/edit/"):
		assert get_query_error(query_string) is None


@pytest.mark.parametrize("query_string,error", [
	("type=nope", "Unknown type"),
	("sort=nope", None),
	("order=sideways", None),
	("limit=abc", None),
])
def test_get_query_error_invalid(query_string, error):
	with app.test_request_context("/dashboards/1/edit/"):
		result = get_query_error(query_string)
		assert result is not None
		if error:
			assert error in result


def test_widget_templates_use_placeholder_index():
	with app.test_request_context("/dashboards/1/edit/"):
		for widget_type, form in make_widget_templates():
			assert form.type.name == "widgets-__index__-type"
			assert form.type.data == widget_type.name
			assert form.removed.data == "0"


def make_form():
	"""Reads the posted form from the current request"""
	from app.blueprints.homepage.editor import DashboardForm
	return DashboardForm(meta={"csrf": False})


def test_dashboard_form_parses_widgets():
	data = {
		"title": "Games",
		"widgets-0-id": "5", "widgets-0-type": "ROW", "widgets-0-removed": "0", "widgets-0-order": "1",
		"widgets-0-title": "Top", "widgets-0-query_string": "/packages/?type=game", "widgets-0-limit": "8",
		# Added in the browser, with a gap in the indices
		"widgets-3-id": "", "widgets-3-type": "TAGS", "widgets-3-removed": "0", "widgets-3-order": "0",
		"widgets-3-title": "", "widgets-3-query_string": "", "widgets-3-limit": "",
	}
	with app.test_request_context("/dashboards/1/edit/", method="POST", data=data):
		form = make_form()
		assert form.validate(), form.errors
		entries = [entry.form for entry in form.widgets.entries]
		assert [(e.type.data, e.order.data) for e in entries] == [("ROW", "1"), ("TAGS", "0")]
		assert entries[0].query_string.data == "type=game"
		assert entries[0].limit.data == 8
		assert entries[1].title.data is None
		assert entries[1].limit.data is None


@pytest.mark.parametrize("fields,error_field", [
	({"widgets-0-type": "ROW", "widgets-0-query_string": "sort=nope"}, "query_string"),
	({"widgets-0-type": "NOPE"}, "type"),
	({"widgets-0-type": "ROW", "widgets-0-limit": "0"}, "limit"),
	({"widgets-0-type": "ROW", "widgets-0-limit": "51"}, "limit"),
])
def test_dashboard_form_invalid(fields, error_field):
	data = {"title": "Home", "widgets-0-removed": "0", **fields}
	with app.test_request_context("/dashboards/1/edit/", method="POST", data=data):
		form = make_form()
		assert not form.validate()
		assert error_field in form.widgets.entries[0].form.errors


def test_dashboard_form_ignores_query_of_removed_widget():
	data = {"title": "Home", "widgets-0-type": "ROW", "widgets-0-removed": "1", "widgets-0-query_string": "sort=nope"}
	with app.test_request_context("/dashboards/1/edit/", method="POST", data=data):
		assert make_form().validate()


def test_widget_card_shows_widget_fields():
	from flask import render_template_string
	from app.blueprints.homepage import WIDGETS
	from app.models import DashboardWidgetType

	with app.test_request_context("/dashboards/1/edit/"):
		templates = dict(make_widget_templates())
		source = '{% from "homepage/editor/macros.html" import render_widget_card %}{{ render_widget_card(sub, cls) }}'

		def render(widget_type):
			return render_template_string(source, sub=templates[widget_type], cls=WIDGETS[widget_type])

		row = render(DashboardWidgetType.ROW)
		assert 'name="widgets-__index__-title"' in row
		assert 'name="widgets-__index__-query_string"' in row
		assert 'name="widgets-__index__-limit"' in row
		assert 'name="widgets-__index__-type"' in row and 'value="ROW"' in row

		tags = render(DashboardWidgetType.TAGS)
		assert 'name="widgets-__index__-title"' in tags
		assert "query_string" not in tags
		assert 'name="widgets-__index__-limit"' not in tags


def test_get_query_error_collection_format():
	# Rejected before looking anything up, so no database is needed
	with app.test_request_context("/dashboards/1/edit/"):
		assert get_query_error("collection=nope") == "Unable to find that collection"


@pytest.mark.parametrize("url,valid", [
	("/gamejam/", True),
	("/packages/?type=game", True),
	("https://jam.luanti.org/", True),
	("http://example.com/path", True),
	("//example.com/", False),
	("/\\example.com", False),
	("javascript:alert(1)", False),
	("data:text/html,hi", False),
	("https://", False),
	("example.com", False),
	("gamejam/", False),
])
def test_is_valid_slide_url(url, valid):
	from app.blueprints.homepage.editor import is_valid_slide_url
	assert is_valid_slide_url(url) == valid


def post_slides(fields: dict, files: dict | None = None):
	from app.blueprints.homepage.editor import SlidesForm
	data = {"slides-0-removed": "0", "slides-0-order": "0", **fields, **(files or {})}
	ctx = app.test_request_context("/dashboards/1/widgets/1/slides/", method="POST", data=data,
			content_type="multipart/form-data")
	ctx.push()
	form = SlidesForm(meta={"csrf": False})
	return ctx, form


def image_file():
	import io
	return (io.BytesIO(b"not checked by the form"), "jam.png")


@pytest.mark.parametrize("fields,files,errors", [
	# New slides need an image
	({"slides-0-title": "Jam", "slides-0-url": "/gamejam/"}, None, {"image"}),
	({"slides-0-title": "Jam", "slides-0-url": "/gamejam/"}, {"slides-0-image": image_file}, set()),
	# Existing slides keep their image
	({"slides-0-id": "3", "slides-0-title": "Jam", "slides-0-url": "/gamejam/"}, None, set()),
	({"slides-0-id": "3", "slides-0-title": "", "slides-0-url": "javascript:alert(1)"}, None, {"title", "url"}),
	({"slides-0-id": "3", "slides-0-title": "Jam", "slides-0-url": "/gamejam/",
		"slides-0-starts_at": "2026-12-01T00:00", "slides-0-ends_at": "2026-11-01T00:00"}, None, {"ends_at"}),
	({"slides-0-id": "3", "slides-0-title": "Jam", "slides-0-url": "/gamejam/",
		"slides-0-starts_at": "2026-11-01T00:00", "slides-0-ends_at": "2026-12-01T00:00"}, None, set()),
	# Removed slides are deleted, so aren't validated
	({"slides-0-removed": "1", "slides-0-title": "", "slides-0-url": ""}, None, set()),
])
def test_slide_form_validation(fields, files, errors):
	files = {key: value() for key, value in (files or {}).items()}
	ctx, form = post_slides(fields, files)
	try:
		form.validate()
		assert set(form.slides.entries[0].form.errors.keys()) == errors
	finally:
		ctx.pop()


def test_slide_form_parses_dates_and_strips_url():
	import datetime
	ctx, form = post_slides({"slides-0-id": "3", "slides-0-title": "Jam", "slides-0-url": "  /gamejam/  ",
			"slides-0-starts_at": "2026-11-01T09:30"})
	try:
		assert form.validate(), form.errors
		sub = form.slides.entries[0].form
		assert sub.url.data == "/gamejam/"
		assert sub.starts_at.data == datetime.datetime(2026, 11, 1, 9, 30)
		assert sub.ends_at.data is None
	finally:
		ctx.pop()


def test_slide_card_template():
	from flask import render_template_string
	from app.blueprints.homepage.editor import SlideForm

	with app.test_request_context("/"):
		template = SlideForm(formdata=None, prefix="slides-__index__-", data={"removed": "0"})
		html = render_template_string(
				'{% from "homepage/editor/macros.html" import render_slide_card %}{{ render_slide_card(sub) }}',
				sub=template)
		for name in ["id", "removed", "order", "title", "description", "label", "url", "image", "starts_at", "ends_at"]:
			assert f'name="slides-__index__-{name}"' in html, name
		assert 'type="file"' in html
		assert 'type="datetime-local"' in html
