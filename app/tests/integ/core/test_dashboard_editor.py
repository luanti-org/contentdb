# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest

from app.models import db, AuditLogEntry, Dashboard, DashboardWidget, DashboardWidgetType, UserRank
from ..factories import create_dashboard, create_user, login_as


def make_dashboard():
	return create_dashboard([
		(DashboardWidgetType.SPOTLIGHT, None, None, 6),
		(DashboardWidgetType.ROW, "Top Games", "type=game&sort=score", 8),
		(DashboardWidgetType.TAGS, "Search by Tags", None, None),
	])


def widget_fields(index: int, widget: DashboardWidget | None, type_: str, order: int, removed: bool = False,
		title: str = "", query_string: str = "", limit: str = "") -> dict[str, str]:
	prefix = f"widgets-{index}-"
	return {
		prefix + "id": str(widget.id) if widget else "",
		prefix + "type": type_,
		prefix + "removed": "1" if removed else "0",
		prefix + "order": str(order),
		prefix + "title": title,
		prefix + "query_string": query_string,
		prefix + "limit": limit,
	}


def get_widgets(dashboard_id: int) -> list[tuple]:
	db.session.expire_all()
	dashboard = db.session.get(Dashboard, dashboard_id)
	assert dashboard is not None
	return [(w.type, w.title, w.query_string, w.limit, w.order) for w in dashboard.widgets.all()]


@pytest.mark.parametrize("url", ["/dashboards/", "/dashboards/new/", "/dashboards/{id}/edit/"])
@pytest.mark.parametrize("rank", [UserRank.MEMBER, UserRank.TRUSTED_MEMBER])
def test_editor_requires_permission(client, url, rank):
	dashboard = make_dashboard()
	login_as(client, create_user("user", rank=rank))

	assert client.get(url.format(id=dashboard.id)).status_code == 403
	if url != "/dashboards/":  # GET only
		assert client.post(url.format(id=dashboard.id), data={"title": "Hacked"}).status_code == 403
	assert get_widgets(dashboard.id)[1][1] == "Top Games"


@pytest.mark.parametrize("url", ["/dashboards/", "/dashboards/new/", "/dashboards/{id}/edit/"])
def test_curator_can_edit_dashboards(client, url):
	dashboard = make_dashboard()
	login_as(client, create_user("curator", rank=UserRank.CURATOR))

	assert client.get(url.format(id=dashboard.id)).status_code == 200


def test_editor_requires_login(client):
	rv = client.get("/dashboards/")
	assert rv.status_code == 302
	assert "/user/login/" in rv.headers["Location"]


def test_editor_list(client):
	create_dashboard([], title="First Dashboard")
	create_dashboard([], title="Second Dashboard")
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	html = client.get("/dashboards/").data.decode("utf-8")
	assert "First Dashboard" in html and "Second Dashboard" in html
	assert html.index("First Dashboard") < html.index("Second Dashboard")


def test_editor_edit_page(client):
	dashboard = make_dashboard()
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	rv = client.get(f"/dashboards/{dashboard.id}/edit/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert 'value="type=game&amp;sort=score"' in html
	assert 'value="Top Games"' in html
	# A template for each widget type, for adding widgets
	assert 'id="widget_template_ROW"' in html
	assert 'name="widgets-__index__-type"' in html


def test_editor_homepage_link(client):
	dashboard = make_dashboard()

	assert b"Edit homepage" not in client.get("/").data

	login_as(client, create_user("editor", rank=UserRank.EDITOR))
	assert f"/dashboards/{dashboard.id}/edit/".encode() in client.get("/").data


def test_editor_save(client):
	dashboard = make_dashboard()
	spotlight, row, tags = dashboard.widgets.all()
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	data = {
		"title": "New Home",
		# Moved to the end
		**widget_fields(0, spotlight, "SPOTLIGHT", 3, limit="4",
				title="Ignored, as spotlights don't have titles"),
		# Edited, pasting a URL
		**widget_fields(1, row, "ROW", 0, title="Best Games", query_string="/packages/?type=game&sort=downloads",
				limit="12"),
		**widget_fields(2, tags, "TAGS", 1, removed=True),
		# Added
		**widget_fields(5, None, "REVIEWS", 2, title="Reviews", limit="3"),
	}
	rv = client.post(f"/dashboards/{dashboard.id}/edit/", data=data)
	assert rv.status_code == 302

	saved = db.session.get(Dashboard, dashboard.id)
	assert saved is not None and saved.title == "New Home"
	assert get_widgets(dashboard.id) == [
		(DashboardWidgetType.ROW, "Best Games", "type=game&sort=downloads", 12, 0),
		(DashboardWidgetType.REVIEWS, "Reviews", None, 3, 1),
		(DashboardWidgetType.SPOTLIGHT, None, None, 4, 2),
	]
	assert AuditLogEntry.query.filter_by(title="Edited dashboard New Home").count() == 1


def test_editor_save_invalid_query(client):
	dashboard = make_dashboard()
	spotlight, row, tags = dashboard.widgets.all()
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	data = {
		"title": "Home",
		**widget_fields(0, spotlight, "SPOTLIGHT", 0, limit="6"),
		**widget_fields(1, row, "ROW", 1, title="Changed", query_string="type=nope"),
		**widget_fields(2, tags, "TAGS", 2, title="Search by Tags"),
	}
	rv = client.post(f"/dashboards/{dashboard.id}/edit/", data=data)
	assert rv.status_code == 200
	assert b"Unknown type" in rv.data
	assert get_widgets(dashboard.id)[1][1] == "Top Games"


@pytest.mark.parametrize("change", ["type", "other_dashboard"])
def test_editor_save_rejects_tampering(client, change):
	dashboard = make_dashboard()
	other = make_dashboard()
	row = dashboard.widgets.all()[1]
	other_row = other.widgets.all()[1]
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	if change == "type":
		fields = widget_fields(0, row, "TAGS", 0, title="Changed")
	else:
		fields = widget_fields(0, other_row, "ROW", 0, title="Changed")

	rv = client.post(f"/dashboards/{dashboard.id}/edit/", data={"title": "Home", **fields})
	assert rv.status_code == 400
	assert get_widgets(other.id)[1][1] == "Top Games"


def test_editor_create(client):
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	data = {
		"title": "Games",
		**widget_fields(0, None, "ROW", 0, title="Top Games", query_string="type=game"),
	}
	rv = client.post("/dashboards/new/", data=data)
	assert rv.status_code == 302

	dashboard = Dashboard.query.filter_by(title="Games").one()
	assert rv.headers["Location"].endswith(f"/dashboards/{dashboard.id}/edit/")
	assert get_widgets(dashboard.id) == [(DashboardWidgetType.ROW, "Top Games", "type=game", None, 0)]
	assert AuditLogEntry.query.filter_by(title="Created dashboard Games").count() == 1
