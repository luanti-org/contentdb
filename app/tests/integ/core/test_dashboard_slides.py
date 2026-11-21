# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""Custom slides in spotlight carousels, and their editor"""

import datetime
import io
import os

import pytest

from app import app
from app.models import db, AuditLogEntry, DashboardWidget, DashboardWidgetSlide, DashboardWidgetType, UserRank
from ..factories import create_collection, create_dashboard, create_package, create_slide, create_user, get_user, \
	login_as, make_image


def make_dashboard():
	dashboard = create_dashboard([
		(DashboardWidgetType.SPOTLIGHT, None, "collection=ContentDB/spotlight&random", 6),
		(DashboardWidgetType.ROW, "Top Mods", "type=mod", 4),
	])
	spotlight, row = dashboard.widgets.all()
	return dashboard, spotlight, row


def slides_url(dashboard, widget) -> str:
	return f"/dashboards/{dashboard.id}/widgets/{widget.id}/slides/"


def slide_fields(index: int, slide: DashboardWidgetSlide | None, order: int, removed: bool = False,
		title: str = "Game Jam", url: str = "/gamejam/", **kwargs) -> dict:
	prefix = f"slides-{index}-"
	fields = {
		"id": str(slide.id) if slide else "",
		"removed": "1" if removed else "0",
		"order": str(order),
		"title": title,
		"description": "",
		"label": "",
		"url": url,
		"starts_at": "",
		"ends_at": "",
		**kwargs,
	}
	return {prefix + key: value for key, value in fields.items()}


def image(data: bytes | None = None, filename: str = "jam.png"):
	return io.BytesIO(data if data is not None else make_image()), filename


def get_slides(widget_id: int) -> list[DashboardWidgetSlide]:
	db.session.expire_all()
	widget = db.session.get(DashboardWidget, widget_id)
	assert widget is not None
	return widget.slides.all()


@pytest.mark.parametrize("rank", [UserRank.MEMBER, UserRank.TRUSTED_MEMBER])
def test_slides_requires_permission(client, rank):
	dashboard, spotlight, _ = make_dashboard()
	login_as(client, create_user("user", rank=rank))

	assert client.get(slides_url(dashboard, spotlight)).status_code == 403
	assert client.post(slides_url(dashboard, spotlight), data=slide_fields(0, None, 0)).status_code == 403


def test_curator_can_edit_slides(client):
	dashboard, spotlight, _ = make_dashboard()
	login_as(client, create_user("curator", rank=UserRank.CURATOR))

	assert client.get(slides_url(dashboard, spotlight)).status_code == 200


def test_slides_only_for_widgets_with_slides(client):
	dashboard, spotlight, row = make_dashboard()
	other, other_spotlight, _ = make_dashboard()
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	assert client.get(slides_url(dashboard, spotlight)).status_code == 200
	assert client.get(slides_url(dashboard, row)).status_code == 404
	# A widget in another dashboard
	assert client.get(f"/dashboards/{dashboard.id}/widgets/{other_spotlight.id}/slides/").status_code == 404


def test_slides_create(client):
	dashboard, spotlight, _ = make_dashboard()
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	data = {
		**slide_fields(0, None, 0, title="Game Jam 2026", url="https://jam.example.com/", label="Competition",
				description="Make a game", starts_at="2026-11-01T00:00", ends_at="2026-12-01T00:00"),
		"slides-0-image": image(),
	}
	rv = client.post(slides_url(dashboard, spotlight), data=data, content_type="multipart/form-data")
	assert rv.status_code == 302, rv.data.decode("utf-8")

	slides = get_slides(spotlight.id)
	assert len(slides) == 1
	slide = slides[0]
	assert (slide.title, slide.url, slide.label, slide.description) == \
			("Game Jam 2026", "https://jam.example.com/", "Competition", "Make a game")
	assert slide.starts_at == datetime.datetime(2026, 11, 1)
	assert slide.ends_at == datetime.datetime(2026, 12, 1)
	assert slide.image_path.startswith("/uploads/")
	assert os.path.isfile(os.path.join(app.config["UPLOAD_DIR"], os.path.basename(slide.image_path)))
	assert AuditLogEntry.query.filter_by(title="Edited slides in dashboard Home").count() == 1

	# Listed on the dashboard editor
	html = client.get(f"/dashboards/{dashboard.id}/edit/").data.decode("utf-8")
	assert f'href="{slides_url(dashboard, spotlight)}"' in html
	assert "Custom slides (1)" in html


def test_slides_edit_reorder_remove(client):
	dashboard, spotlight, _ = make_dashboard()
	first = create_slide(spotlight, "First", order=0)
	second = create_slide(spotlight, "Second", order=1)
	third = create_slide(spotlight, "Third", order=2)
	second_image = second.image_path
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	data = {
		# Edited without a new image, which keeps the old one
		**slide_fields(0, first, 1, removed=True),
		**slide_fields(1, second, 1, title="Second edited", url="/packages/"),
		**slide_fields(2, third, 0, title="Third"),
	}
	rv = client.post(slides_url(dashboard, spotlight), data=data, content_type="multipart/form-data")
	assert rv.status_code == 302, rv.data.decode("utf-8")

	slides = get_slides(spotlight.id)
	assert [(slide.title, slide.order) for slide in slides] == [("Third", 0), ("Second edited", 1)]
	assert slides[1].image_path == second_image
	assert slides[1].url == "/packages/"


def test_slides_new_needs_image(client):
	dashboard, spotlight, _ = make_dashboard()
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	rv = client.post(slides_url(dashboard, spotlight), data=slide_fields(0, None, 0),
			content_type="multipart/form-data")
	assert rv.status_code == 200
	assert b"An image is required" in rv.data
	assert get_slides(spotlight.id) == []


def test_slides_invalid_image(client):
	dashboard, spotlight, _ = make_dashboard()
	existing = create_slide(spotlight, "Existing")
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	data = {
		**slide_fields(0, existing, 0, title="Changed"),
		**slide_fields(1, None, 1),
		"slides-1-image": image(b"not an image"),
	}
	rv = client.post(slides_url(dashboard, spotlight), data=data, content_type="multipart/form-data")
	assert rv.status_code == 200
	assert b"isn&#39;t actually an image" in rv.data or b"isn't actually an image" in rv.data

	# Nothing was saved
	assert [slide.title for slide in get_slides(spotlight.id)] == ["Existing"]


def test_slides_rejects_other_widgets_slide(client):
	dashboard, spotlight, _ = make_dashboard()
	other, other_spotlight, _ = make_dashboard()
	other_slide = create_slide(other_spotlight, "Other")
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	rv = client.post(slides_url(dashboard, spotlight), data=slide_fields(0, other_slide, 0, title="Hijacked"),
			content_type="multipart/form-data")
	assert rv.status_code == 400
	assert [slide.title for slide in get_slides(other_spotlight.id)] == ["Other"]


def test_slides_deleted_with_widget(client):
	dashboard, spotlight, row = make_dashboard()
	slide = create_slide(spotlight)
	slide_id = slide.id
	login_as(client, create_user("editor", rank=UserRank.EDITOR))

	prefix0, prefix1 = "widgets-0-", "widgets-1-"
	data = {
		"title": "Home",
		prefix0 + "id": str(spotlight.id), prefix0 + "type": "SPOTLIGHT", prefix0 + "removed": "1", prefix0 + "order": "0",
		prefix1 + "id": str(row.id), prefix1 + "type": "ROW", prefix1 + "removed": "0", prefix1 + "order": "1",
		prefix1 + "title": "Top Mods", prefix1 + "query_string": "type=mod",
	}
	rv = client.post(f"/dashboards/{dashboard.id}/edit/", data=data)
	assert rv.status_code == 302

	db.session.expire_all()
	assert db.session.get(DashboardWidgetSlide, slide_id) is None


def test_homepage_shows_active_slides_first(client):
	author = create_user("author")
	mod = create_package("SomeMod", author)
	create_collection(get_user("ContentDB"), [mod], name="spotlight")
	dashboard, spotlight, _ = make_dashboard()

	now = datetime.datetime.utcnow()
	day = datetime.timedelta(days=1)
	create_slide(spotlight, "Always Shown", order=0)
	create_slide(spotlight, "Currently Running", order=1, starts_at=now - day, ends_at=now + day)
	create_slide(spotlight, "Not Started", order=2, starts_at=now + day)
	create_slide(spotlight, "Already Ended", order=3, ends_at=now - day)

	html = client.get("/").data.decode("utf-8")
	carousel = html[html.index(f'id="spotlight-{spotlight.id}"'):html.index("Top Mods")]

	assert "Not Started" not in carousel
	assert "Already Ended" not in carousel
	assert carousel.index("Always Shown") < carousel.index("Currently Running") < carousel.index(mod.title)

	# Custom slides link where they're set to, with their label, and without "by"
	assert 'href="https://jam.example.com/"' in carousel
	assert "Competition" in carousel
	assert "Always Shown</strong> by" not in carousel
	# 3 slides: 2 custom and 1 package
	assert carousel.count('data-bs-slide-to=') == 3


def test_homepage_slides_without_packages(client):
	"""Slides show even if the query finds no packages"""
	dashboard, spotlight, _ = make_dashboard()
	create_slide(spotlight, "Only Slide")

	html = client.get("/").data.decode("utf-8")
	assert f'id="spotlight-{spotlight.id}"' in html
	assert "Only Slide" in html


def upload_dir_listing() -> set[str]:
	return set(os.listdir(app.config["UPLOAD_DIR"]))


def test_slides_failed_save_leaves_no_uploads(client):
	dashboard, spotlight, _ = make_dashboard()
	other, other_spotlight, _ = make_dashboard()
	other_slide = create_slide(other_spotlight, "Other")
	login_as(client, create_user("editor", rank=UserRank.EDITOR))
	before = upload_dir_listing()

	# A valid image followed by an invalid one
	data = {
		**slide_fields(0, None, 0, title="Valid"),
		"slides-0-image": image(),
		**slide_fields(1, None, 1, title="Invalid"),
		"slides-1-image": image(b"not an image"),
	}
	rv = client.post(slides_url(dashboard, spotlight), data=data, content_type="multipart/form-data")
	assert rv.status_code == 200
	assert upload_dir_listing() == before

	# A valid image followed by another widget's slide
	data = {
		**slide_fields(0, None, 0, title="Valid"),
		"slides-0-image": image(),
		**slide_fields(1, other_slide, 1, title="Hijacked"),
	}
	rv = client.post(slides_url(dashboard, spotlight), data=data, content_type="multipart/form-data")
	assert rv.status_code == 400
	assert upload_dir_listing() == before
	assert get_slides(spotlight.id) == []
