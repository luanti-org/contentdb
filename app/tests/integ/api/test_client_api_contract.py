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
from app.models import db, PackageState, PackageAlias, MetaPackage, Dependency, LuantiRelease, PackageRelease
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
