# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
import xml.etree.ElementTree as ET

from app import app
from app.models import db, PackageState, PackageType, Tag
from ..factories import create_collection, create_package, create_release, create_user

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def base_url() -> str:
	return app.config["BASE_URL"].rstrip("/")


def get_sitemap(client) -> dict[str, str | None]:
	"""Returns a map from URL to lastmod"""
	rv = client.get("/sitemap.xml")
	assert rv.status_code == 200
	assert rv.mimetype == "application/xml"
	assert rv.cache_control.public

	root = ET.fromstring(rv.data)  # noqa: S314 - parses our own test output
	ret = {}
	for url in root.findall("sm:url", NS):
		loc = url.find("sm:loc", NS)
		assert loc is not None and loc.text is not None
		lastmod = url.find("sm:lastmod", NS)
		ret[loc.text] = lastmod.text if lastmod is not None else None
	return ret


def test_sitemap_contents(client):
	author = create_user("author")
	create_user("nopackages")

	mod = create_package("SomeMod", author)
	mod.approved_at = datetime.datetime(2026, 1, 1)
	release = create_release(mod)
	release.created_at = datetime.datetime(2026, 3, 4, 12, 0)

	game = create_package("SomeGame", author, type=PackageType.GAME)
	game.approved_at = datetime.datetime(2026, 2, 3)

	tag = Tag("Some Tag")
	tag.packages.append(mod)
	db.session.add(tag)
	db.session.add(Tag("Empty Tag"))

	create_package("Draft", create_user("drafter"), state=PackageState.WIP)
	create_collection(author, [mod], name="favs")
	create_collection(author, [mod], name="secret", private=True)
	create_collection(author, [], name="empty")
	create_collection(author, [mod], name="favorites")
	db.session.commit()

	urls = get_sitemap(client)
	base = base_url()

	assert urls[f"{base}/"] is None
	assert f"{base}/packages/?type=mod" in urls
	assert f"{base}/packages/?type=game" in urls
	assert f"{base}/packages/?type=txp" in urls
	assert f"{base}/packages/?tag=some_tag" in urls
	assert f"{base}/packages/?tag=empty_tag" not in urls

	# lastmod is the latest of the approved release and approval dates
	assert urls[f"{base}/packages/author/somemod/"] == "2026-03-04"
	assert urls[f"{base}/packages/author/somegame/"] == "2026-02-03"
	assert f"{base}/packages/author/somegame/hub/" in urls
	assert f"{base}/packages/author/somemod/hub/" not in urls
	assert f"{base}/packages/drafter/draft/" not in urls

	assert f"{base}/users/author/" in urls
	assert f"{base}/users/nopackages/" not in urls
	assert f"{base}/users/drafter/" not in urls

	assert f"{base}/collections/author/favs/" in urls
	assert f"{base}/collections/author/secret/" not in urls
	assert f"{base}/collections/author/empty/" not in urls
	assert f"{base}/collections/author/favorites/" not in urls


def test_sitemap_urls_are_indexable(client):
	"""The sitemap shouldn't list pages that tell search engines not to index them"""
	author = create_user("author")
	mod = create_package("SomeMod", author)
	create_package("SomeGame", author, type=PackageType.GAME)
	tag = Tag("Some Tag")
	tag.packages.append(mod)
	db.session.add(tag)
	create_collection(author, [mod], name="favs")
	db.session.commit()

	base = base_url()
	for url in get_sitemap(client):
		path = url.removeprefix(base)
		rv = client.get(path)
		assert rv.status_code == 200, path
		assert b'name="robots" content="noindex"' not in rv.data, path
