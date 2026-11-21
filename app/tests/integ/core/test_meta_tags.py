# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import json
import os

from bs4 import BeautifulSoup

from app import app
from app.models import db
from ..factories import create_collection, create_package, create_screenshot, create_thread, create_user


def get_soup(client, url: str) -> BeautifulSoup:
	rv = client.get(url)
	assert rv.status_code == 200, url
	return BeautifulSoup(rv.data.decode("utf-8"), "html.parser")


def og(soup: BeautifulSoup, prop: str) -> str | None:
	tag = soup.find("meta", attrs={"property": f"og:{prop}"})
	return tag.get("content") if tag else None  # type: ignore[return-value]


def meta(soup: BeautifulSoup, name: str) -> str | None:
	tag = soup.find("meta", attrs={"name": name})
	return tag.get("content") if tag else None  # type: ignore[return-value]


def canonical(soup: BeautifulSoup) -> str | None:
	tag = soup.find("link", rel="canonical")
	return tag.get("href") if tag else None  # type: ignore[return-value]


def base_url() -> str:
	return app.config["BASE_URL"].rstrip("/")


def test_package_page_meta(client):
	author = create_user("author")
	package = create_package("SomeMod", author)
	screenshot = create_screenshot(package)

	soup = get_soup(client, "/packages/author/somemod/")

	assert soup.html is not None and soup.html.get("lang") == "en"
	# Open Graph uses the property attribute, not name
	assert soup.find("meta", attrs={"name": "og:title"}) is None
	assert og(soup, "title") == package.title
	assert og(soup, "description") == package.short_desc
	assert meta(soup, "description") == package.short_desc
	assert og(soup, "site_name") == app.config["USER_APP_NAME"]
	assert og(soup, "type") == "website"

	url = f"{base_url()}/packages/author/somemod/"
	assert canonical(soup) == url
	assert og(soup, "url") == url

	# The large thumbnail, as PNG, with an absolute URL
	filename = os.path.splitext(os.path.basename(screenshot.upload_path))[0]
	assert og(soup, "image") == f"{base_url()}/thumbnails/4/{filename}.png"
	assert og(soup, "image:alt") == package.title
	assert meta(soup, "twitter:card") == "summary_large_image"


def test_package_page_meta_no_screenshot(client):
	author = create_user("author")
	create_package("SomeMod", author)

	soup = get_soup(client, "/packages/author/somemod/")
	assert og(soup, "image") is None
	assert meta(soup, "twitter:card") == "summary"


def test_profile_meta_default_avatar(client):
	create_user("someone")

	soup = get_soup(client, "/users/someone/")
	assert og(soup, "type") == "profile"
	assert canonical(soup) == f"{base_url()}/users/someone/"
	assert og(soup, "image") == f"{base_url()}/static/default_avatar.png"
	assert meta(soup, "twitter:card") == "summary"


def test_profile_meta_cdn_avatar(client):
	user = create_user("someone")
	user.profile_pic = "https://cdn.example.com/avatar.png"
	db.session.commit()

	soup = get_soup(client, "/users/someone/")
	assert og(soup, "image") == "https://cdn.example.com/avatar.png"
	assert user.get_profile_pic_url(absolute=True) == "https://cdn.example.com/avatar.png"


def test_thread_meta(client):
	author = create_user("author")
	thread = create_thread(author, title="Some thread", comment="Hello world")

	soup = get_soup(client, f"/threads/{thread.id}/")
	assert og(soup, "type") == "article"
	assert og(soup, "description") == "Hello world"
	assert canonical(soup) == f"{base_url()}/threads/{thread.id}/"
	assert og(soup, "image") == f"{base_url()}/static/default_avatar.png"


def test_collection_meta(client):
	author = create_user("author")
	package = create_package("SomeMod", author)
	screenshot = create_screenshot(package)
	create_collection(author, [package], name="favs")

	soup = get_soup(client, "/collections/author/favs/")
	assert canonical(soup) == f"{base_url()}/collections/author/favs/"
	filename = os.path.splitext(os.path.basename(screenshot.upload_path))[0]
	assert og(soup, "image") == f"{base_url()}/thumbnails/4/{filename}.png"
	assert meta(soup, "twitter:card") == "summary_large_image"


def test_noindex_page_has_no_canonical(client):
	soup = get_soup(client, "/packages/?q=foo")
	assert meta(soup, "robots") == "noindex"
	assert canonical(soup) is None
	assert og(soup, "url") == f"{base_url()}/packages/?q=foo"


def test_homepage_structured_data(client):
	soup = get_soup(client, "/")
	assert canonical(soup) == f"{base_url()}/"

	script = soup.find("script", type="application/ld+json")
	assert script is not None and script.string is not None
	data = json.loads(script.string)
	assert data["url"] == f"{base_url()}/"
	assert data["potentialAction"]["target"] == f"{base_url()}/packages/?q={{search_term_string}}"
