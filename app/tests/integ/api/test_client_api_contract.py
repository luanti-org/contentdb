# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
The JSON shape of the endpoints that Luanti and other clients rely on. A change here can break released clients,
so these state the expected output exactly.
"""

from typing import Any

import pytest

from app import app
from app.models import db, PackageState, PackageAlias, MetaPackage, Dependency, LuantiRelease, PackageRelease, \
	ReleaseState
from ..factories import create_user, create_package, create_release, create_screenshot, client_request


SHORT_DESC = "The content library should not be used yet as it is still in alpha"


def luanti(name: str) -> LuantiRelease:
	return LuantiRelease.query.filter_by(name=name).one()


class Scenario:
	"""
	owner/pkg: approved, with releases for old and new Luanti versions, an unapproved newer release, an alias,
		dependencies and a screenshot.
	owner/lib: approved, with a release only for Luanti 5.0.
	owner/wip: not approved, so must not appear anywhere.
	"""

	def __init__(self):
		owner = create_user("owner")

		self.lib = create_package("lib", owner)
		self.lib.score = 5
		self.lib.provides.append(MetaPackage("lib"))
		self.lib_release = create_release(self.lib, "1.0")
		self.lib_release.max_rel = luanti("5.0")

		self.pkg = create_package("pkg", owner)
		self.pkg.score = 10
		self.pkg.repo = "https://example.com/owner/pkg.git"
		self.pkg.provides.append(MetaPackage("pkg"))
		self.pkg.provides.append(MetaPackage("pkg_extra"))
		db.session.add(Dependency(self.pkg, meta=MetaPackage.query.filter_by(name="lib").one()))
		db.session.add(Dependency(self.pkg, meta=MetaPackage("opt"), optional=True))
		alias = PackageAlias("oldauthor", "oldname")
		alias.package = self.pkg
		db.session.add(alias)

		self.old_release = create_release(self.pkg, "1.0")
		self.old_release.max_rel = luanti("5.4")
		self.new_release = create_release(self.pkg, "2.0")
		self.new_release.min_rel = luanti("5.5")
		self.new_release.file_size_bytes = 2048
		create_release(self.pkg, "3.0", approved=False)
		self.screenshot = create_screenshot(self.pkg)

		self.wip = create_package("wip", owner, state=PackageState.WIP)
		create_release(self.wip, "1.0")
		db.session.commit()


@pytest.fixture
def scenario(client) -> Scenario:
	return Scenario()


def get_json(client, url: str) -> Any:
	rv = client_request(client, "GET", url)
	assert rv.status_code == 200, rv.data
	return rv.json


def base_url() -> str:
	return app.config["BASE_URL"]


def thumbnail(scenario: Scenario) -> str:
	return base_url() + scenario.screenshot.get_thumb_url(1, legacy=True)


def pkg_short(scenario: Scenario, release: PackageRelease | None) -> dict[str, Any]:
	return {
		"name": "pkg",
		"title": "pkg",
		"author": "owner",
		"short_description": SHORT_DESC,
		"type": "mod",
		"release": release and release.id,
		"thumbnail": thumbnail(scenario),
		"aliases": ["oldauthor/oldname"],
	}


def lib_short(scenario: Scenario) -> dict[str, Any]:
	return {
		"name": "lib",
		"title": "lib",
		"author": "owner",
		"short_description": SHORT_DESC,
		"type": "mod",
		"release": scenario.lib_release.id,
		"thumbnail": None,
	}


def test_packages(client, scenario):
	assert get_json(client, "/api/packages/") == [pkg_short(scenario, scenario.new_release), lib_short(scenario)]


@pytest.mark.parametrize("query,release", [
	("protocol_version=39", "old"),
	("engine_version=5.4", "old"),
	("engine_version=5.6", "new"),
])
def test_packages_for_version(client, scenario, query, release):
	"""
	Packages without a release for the client's version are left out.
	"""
	expected = scenario.old_release if release == "old" else scenario.new_release
	assert get_json(client, f"/api/packages/?{query}") == [pkg_short(scenario, expected)]


def test_packages_keys(client, scenario):
	assert get_json(client, "/api/packages/?fmt=keys") == [
		{"name": "pkg", "author": "owner", "type": "mod"},
		{"name": "lib", "author": "owner", "type": "mod"},
	]


def test_packages_vcs(client, scenario):
	result = get_json(client, "/api/packages/?fmt=vcs")
	assert [x["repo"] for x in result] == ["https://example.com/owner/pkg.git", None]


def test_updates(client, scenario):
	assert get_json(client, "/api/updates/") == {
		"owner/pkg": scenario.new_release.id,
		"owner/lib": scenario.lib_release.id,
		"oldauthor/oldname": scenario.new_release.id,
	}


def test_updates_for_version(client, scenario):
	assert get_json(client, "/api/updates/?protocol_version=39") == {
		"owner/pkg": scenario.old_release.id,
		"oldauthor/oldname": scenario.old_release.id,
	}


def test_dependencies(client, scenario):
	assert get_json(client, "/api/dependencies/") == {
		"page": 1,
		"per_page": 100,
		"page_count": 1,
		"total": 2,
		"urls": {"previous": None, "next": None},
		"items": [
			{
				"type": "mod",
				"author": "owner",
				"name": "pkg",
				"provides": ["pkg", "pkg_extra"],
				"depends": ["lib"],
				"optional_depends": ["opt"],
			},
			{
				"type": "mod",
				"author": "owner",
				"name": "lib",
				"provides": ["lib"],
				"depends": [],
				"optional_depends": [],
			},
		],
	}


def test_dependencies_pagination(client, scenario):
	result = get_json(client, "/api/dependencies/?n=1&page=1")
	assert (result["page"], result["per_page"], result["page_count"], result["total"]) == (1, 1, 2, 2)
	assert result["urls"]["previous"] is None
	assert result["urls"]["next"] == base_url() + "/api/dependencies/?n=1&page=2"
	assert [x["name"] for x in result["items"]] == ["pkg"]


HYPERTEXT_KEYS = {"head", "body", "links", "images", "image_tooltips"}

FOR_CLIENT_KEYS = {
	"author", "maintainers", "state", "dev_state", "ai_disclosure", "name", "title", "short_description",
	"long_description", "type", "created_at", "approved_at", "license", "media_license", "repo", "website",
	"issue_tracker", "forums", "forum_url", "video_url", "video_thumbnail_url", "donate_url", "translation_url",
	"tags", "content_warnings", "provides", "thumbnail", "screenshots", "url", "release", "score", "downloads",
	"supports_all_games", "game_support", "info_hypertext", "download_size", "reviews",
}


def test_for_client(client, scenario):
	result = get_json(client, "/api/packages/owner/pkg/for-client/?formspec_version=7")

	assert set(result) == FOR_CLIENT_KEYS
	assert result["author"] == "owner"
	assert result["name"] == "pkg"
	assert result["type"] == "mod"
	assert result["release"] == scenario.new_release.id
	assert result["download_size"] == "2 KB"
	assert result["url"] == base_url() + "/packages/owner/pkg/download/"
	assert result["provides"] == ["pkg", "pkg_extra"]
	assert result["reviews"] == {"positive": 0, "neutral": 0, "negative": 0}
	assert result["screenshots"] == [{"title": "Screenshot", "url": scenario.screenshot.legacy_public_url}]

	# Descriptions are converted to hypertext for formspecs
	assert set(result["long_description"]) == HYPERTEXT_KEYS
	assert result["long_description"]["body"] == "This is the long desc\n"
	assert set(result["info_hypertext"]) == HYPERTEXT_KEYS


def test_for_client_version(client, scenario):
	result = get_json(client, "/api/packages/owner/pkg/for-client/?formspec_version=7&protocol_version=39")
	assert result["release"] == scenario.old_release.id


def test_for_client_newer_than_max(client, scenario):
	# lib's only release supports up to Luanti 5.0
	result = get_json(client, "/api/packages/owner/lib/for-client/?formspec_version=7&protocol_version=39")
	assert result["release"] is None


def test_for_client_needs_formspec_version(client, scenario):
	rv = client_request(client, "GET", "/api/packages/owner/pkg/for-client/")
	assert rv.status_code == 400
	assert rv.json == {"success": False, "error": "formspec_version is required"}


def test_for_client_reviews(client, scenario):
	result = get_json(client, "/api/packages/owner/pkg/for-client/reviews/?formspec_version=7")
	assert set(result) == HYPERTEXT_KEYS
	assert "No reviews available." in result["body"]


HOMEPAGE_KEYS = {"count", "downloads", "spotlight", "new", "updated", "pop_mod", "pop_txp", "pop_game",
		"high_reviewed"}


def test_homepage(client, scenario):
	scenario.pkg.downloads = 7
	scenario.lib.downloads = 3
	db.session.commit()

	result = get_json(client, "/api/homepage/")

	assert set(result) == HOMEPAGE_KEYS
	assert result["count"] == 2
	# Includes downloads of every package, as a site-wide total
	assert result["downloads"] == 10
	assert [x["name"] for x in result["pop_mod"]] == ["pkg", "lib"]
	assert result["pop_txp"] == []
	assert result["pop_game"] == []
	assert result["high_reviewed"] == []
	for key in ["new", "updated", "pop_mod"]:
		assert "wip" not in [x["name"] for x in result[key]], key

	assert result["pop_mod"][0] == {**pkg_short(scenario, scenario.new_release)}


def test_wip_package_is_hidden(client, scenario):
	assert "wip" not in [x["name"] for x in get_json(client, "/api/packages/")]
	assert "owner/wip" not in get_json(client, "/api/updates/")
	assert "wip" not in [x["name"] for x in get_json(client, "/api/dependencies/")["items"]]


def test_unapproved_release_is_never_offered(client, scenario):
	newest = PackageRelease.query.filter_by(name="3.0").one()
	assert newest.state == ReleaseState.UNAPPROVED

	assert newest.id not in [x["release"] for x in get_json(client, "/api/packages/")]
	assert newest.id not in get_json(client, "/api/updates/").values()
	assert get_json(client, "/api/packages/owner/pkg/")["release"] != newest.id
