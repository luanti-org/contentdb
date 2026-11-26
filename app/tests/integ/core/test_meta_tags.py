# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import json
import os

from bs4 import BeautifulSoup

from app import app
import pytest

from app.models import db, Dependency, MetaPackage
from ..factories import create_collection, create_package, create_release, create_review, create_screenshot, \
	create_thread, create_user


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
	create_package("SomeMod", create_user("someone"))

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


def is_noindex(client, url: str) -> bool:
	return meta(get_soup(client, url), "robots") == "noindex"


@pytest.mark.parametrize("url", ["/user/login/", "/user/login/?next=%2Fpackages%2F", "/user/register/",
		"/user/forgot-password/", "/report/", "/report/?url=/threads/1/"])
def test_noindex_utility_pages(client, url):
	assert is_noindex(client, url)


def test_noindex_package_subpages(client):
	author = create_user("author")
	package = create_package("SomeMod", author)
	release = create_release(package)

	assert not is_noindex(client, "/packages/author/somemod/")
	assert is_noindex(client, "/packages/author/somemod/releases/")
	assert is_noindex(client, f"/packages/author/somemod/releases/{release.id}/")
	assert is_noindex(client, "/packages/author/somemod/similar/")


def test_noindex_download_redirects(client):
	author = create_user("author")
	package = create_package("SomeMod", author)
	release = create_release(package)

	for url in ["/packages/author/somemod/download/", f"/packages/author/somemod/releases/{release.id}/download/"]:
		rv = client.get(url)
		assert rv.status_code == 302, url
		assert rv.headers.get("X-Robots-Tag") == "noindex", url


def test_robots_txt_does_not_hide_noindex_pages():
	# A disallowed URL can't be crawled, so search engines never see its noindex and index the bare URL
	with open(os.path.join(app.root_path, "public", "robots.txt")) as f:
		text = f.read()
	assert "/report/" not in text
	assert "/download/" not in text


def test_noindex_package_list_sort(client):
	assert not is_noindex(client, "/packages/")
	assert not is_noindex(client, "/packages/?type=mod")
	assert is_noindex(client, "/packages/?type=mod&sort=name")
	assert is_noindex(client, "/packages/?order=asc")


def test_noindex_empty_profile(client):
	create_user("empty")
	assert is_noindex(client, "/users/empty/")


def test_profile_with_package_is_indexed(client):
	author = create_user("author")
	create_package("SomeMod", author)
	assert not is_noindex(client, "/users/author/")


def test_profile_with_review_is_indexed(client):
	author = create_user("author")
	reviewer = create_user("reviewer")
	create_review(reviewer, create_package("SomeMod", author))
	assert not is_noindex(client, "/users/reviewer/")


def test_noindex_modname_with_few_dependers(client):
	author = create_user("author")
	meta_package = MetaPackage("somedep")
	db.session.add(meta_package)
	db.session.add(Dependency(create_package("ModA", author), meta=meta_package))
	db.session.commit()
	assert is_noindex(client, "/modnames/somedep/")

	db.session.add(Dependency(create_package("ModB", author), meta=meta_package, optional=True))
	db.session.commit()
	assert not is_noindex(client, "/modnames/somedep/")


@pytest.mark.parametrize("url", ["/packages/author/somemod/add-to/", "/packages/author/somemod/threads/new/",
		"/packages/author/somemod/stats/?start=2026-02-15&end=2026-02-22"])
def test_noindex_login_redirect(client, url):
	create_package("SomeMod", create_user("author"))

	rv = client.get(url)
	assert rv.status_code == 302
	assert rv.headers["Location"].startswith("/user/login/")
	assert rv.headers.get("X-Robots-Tag") == "noindex"


def test_other_redirects_are_indexable(client):
	create_package("SomeMod", create_user("author"))

	rv = client.get("/packages/author/")
	assert 300 <= rv.status_code < 400
	assert "X-Robots-Tag" not in rv.headers


def test_noindex_collections_filtered_by_package(client):
	author = create_user("author")
	package = create_package("SomeMod", author)
	create_collection(author, [package], name="favs")

	assert not is_noindex(client, "/collections/")
	assert is_noindex(client, "/collections/?package=author/somemod")


def test_homepage_structured_data(client):
	soup = get_soup(client, "/")
	assert canonical(soup) == f"{base_url()}/"

	script = soup.find("script", type="application/ld+json")
	assert script is not None and script.string is not None
	data = json.loads(script.string)
	assert data["url"] == f"{base_url()}/"
	assert data["potentialAction"]["target"] == f"{base_url()}/packages/?q={{search_term_string}}"
