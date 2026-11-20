# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2026 rubenwardy <rw@rubenwardy>

import pytest

from app.default_data import populate_test_data
from app.models import db, DashboardWidgetType, PackageType
from ..factories import create_collection, create_dashboard, create_package, create_review, create_screenshot, \
	create_user, get_user, login_as


# The same as the default homepage, seeded by migration fa25785307b1. recreate_db() deletes it, so tests make their own.
DEFAULT_WIDGETS = [
	(DashboardWidgetType.SPOTLIGHT, None, "collection=ContentDB/spotlight&random", 6),
	(DashboardWidgetType.ROW, "Recently Added", "sort=approved_at&order=desc", 4),
	(DashboardWidgetType.ROW, "Recently Updated", "sort=last_release&order=desc", 4),
	(DashboardWidgetType.ROW, "Top Games", "type=game&sort=score&order=desc", 8),
	(DashboardWidgetType.ROW, "Top Mods", "type=mod&sort=score&order=desc", 8),
	(DashboardWidgetType.ROW, "Top Texture Packs", "type=txp&sort=score&order=desc", 8),
	(DashboardWidgetType.TAGS, "Search by Tags", None, None),
	(DashboardWidgetType.ROW, "Highest Reviewed", "sort=reviews&order=desc", 4),
	(DashboardWidgetType.REVIEWS, "Recent Positive Reviews", None, 5),
]


def test_homepage_no_dashboard(client):
	rv = client.get("/")
	assert rv.status_code == 404


def test_homepage_empty(client):
	"""Start with a blank database."""
	create_dashboard(DEFAULT_WIDGETS)

	rv = client.get("/")
	assert rv.status_code == 200
	assert b"No packages available" in rv.data and b"packagecard" not in rv.data
	assert b"Top Games" in rv.data


def test_homepage_with_contents(client):
	"""Start with a test database."""
	create_dashboard(DEFAULT_WIDGETS)
	populate_test_data(db.session)
	db.session.commit()

	rv = client.get("/")
	assert rv.status_code == 200
	assert b"packagecard" in rv.data


def test_homepage_widgets(client):
	author = create_user("author")
	reviewer = create_user("reviewer")
	game = create_package("SomeGame", author, type=PackageType.GAME)
	mod = create_package("SomeMod", author)
	create_collection(get_user("ContentDB"), [mod], name="spotlight")
	create_review(reviewer, mod, comment="This mod is great")
	dashboard = create_dashboard(DEFAULT_WIDGETS)

	rv = client.get("/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")

	# Spotlight only contains packages in the ContentDB/spotlight collection
	spotlight_id = dashboard.widgets.all()[0].id
	assert f'id="spotlight-{spotlight_id}"' in html
	spotlight = html[html.index(f'id="spotlight-{spotlight_id}"'):html.index("Recently Added")]
	assert mod.title in spotlight and game.title not in spotlight

	# Rows only contain packages matching their query
	top_games = html[html.index("Top Games"):html.index("Top Mods")]
	assert game.title in top_games and mod.title not in top_games
	assert 'href="/packages/?type=game&amp;sort=score&amp;order=desc"' in html

	# Reviews
	assert "This mod is great" in html

	# Logged out, so no voting script
	assert "quick_review_voting.js" not in html


def test_homepage_widget_order(client):
	create_dashboard([
		(DashboardWidgetType.ROW, "Second Row Title", "type=mod", 4),
		(DashboardWidgetType.ROW, "First Row Title", "type=game", 4),
	])

	html = client.get("/").data.decode("utf-8")
	assert html.index("Second Row Title") < html.index("First Row Title")


def test_homepage_row_title_defaults_to_query(client):
	create_dashboard([
		(DashboardWidgetType.ROW, None, "type=game", 4),
	])

	html = client.get("/").data.decode("utf-8")
	assert "<h2 class=\"mb-3\">Games</h2>" in html


def test_homepage_row_limit(client):
	author = create_user("author")
	for i in range(3):
		create_package(f"mod{i}", author)
	create_dashboard([
		(DashboardWidgetType.ROW, "Mods", "type=mod", 2),
	])

	html = client.get("/").data.decode("utf-8")
	assert html.count("packagecard") == 2


def test_homepage_broken_widget_is_skipped(client, monkeypatch):
	"""A widget that fails to render is skipped, rather than taking down the whole homepage."""
	from app.blueprints.homepage.widgets.tags import TagsWidget

	def fail(self):
		raise Exception("Broken widget")

	# Invalid stored queries fall back rather than failing, see test_homepage_bad_sort_falls_back
	monkeypatch.setattr(TagsWidget, "get_context", fail)
	create_dashboard([
		(DashboardWidgetType.TAGS, "Broken Row", None, None),
		(DashboardWidgetType.ROW, "Working Row", "type=mod", 4),
	])

	rv = client.get("/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "Broken Row" not in html
	assert "Working Row" in html


def test_homepage_reviews_script_when_logged_in(client):
	create_dashboard([
		(DashboardWidgetType.REVIEWS, "Reviews", None, 5),
	])
	login_as(client, create_user("someone"))

	html = client.get("/").data.decode("utf-8")
	assert html.count("quick_review_voting.js") == 1


def test_homepage_missing_collection_shows_nothing(client):
	"""A widget whose collection was deleted shows no packages, rather than every package"""
	author = create_user("author")
	create_package("SomeMod", author)
	create_dashboard([
		(DashboardWidgetType.ROW, "Deleted Collection", "collection=author/deleted", 4),
	])

	html = client.get("/").data.decode("utf-8")
	assert "Deleted Collection" in html
	assert "packagecard" not in html
	assert "No packages available" in html


def test_homepage_amp_in_url(client):
	"""The &amp bot check is for the page's own query, not the widgets' stored queries"""
	author = create_user("author")
	create_package("SomeMod", author)
	create_dashboard([
		(DashboardWidgetType.ROW, "Some Row", "type=mod", 4),
	])

	rv = client.get("/?utm_source=mail&amp;x=1")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "Some Row" in html
	assert "packagecard" in html


@pytest.mark.parametrize("query_string", [
	"game=nobody/nogame",
	"author=nobody",
	"tag=no_such_tag",
	"type=mod&tag=no_such_tag",
	"license=No-Such-License",
])
def test_homepage_stale_query_shows_nothing(client, query_string):
	"""A widget whose query refers to something deleted shows no packages, rather than vanishing or showing all"""
	author = create_user("author")
	create_package("SomeMod", author)
	create_dashboard([
		(DashboardWidgetType.ROW, "Stale Row", query_string, 4),
	])

	rv = client.get("/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "Stale Row" in html
	assert "packagecard" not in html
	assert "No packages available" in html


def test_homepage_bad_sort_falls_back(client):
	author = create_user("author")
	create_package("SomeMod", author)
	create_dashboard([
		(DashboardWidgetType.ROW, "Bad Sort", "sort=nope&order=sideways&limit=abc", 4),
	])

	html = client.get("/").data.decode("utf-8")
	assert "Bad Sort" in html
	assert "packagecard" in html


def test_homepage_random_keeps_screenshots(client):
	"""
	With subqueryload, the screenshot query re-ran the random query and picked different packages, so some tiles
	were missing their screenshot.
	"""
	author = create_user("author")
	for i in range(30):
		create_screenshot(create_package(f"mod{i}", author))
	create_dashboard([
		(DashboardWidgetType.ROW, "Random", "random", 3),
		(DashboardWidgetType.SPOTLIGHT, None, "random", 3),
	])

	for _ in range(3):
		html = client.get("/").data.decode("utf-8")
		assert html.count("packagecard") == 3
		assert "/static/placeholder.png" not in html
