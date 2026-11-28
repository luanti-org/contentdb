# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Editing packages through the API, with PUT /api/packages/<author>/<name>/.
"""

import pytest

from app.models import db, Package, PackageState, AuditLogEntry, Tag, ContentWarning
from app.domain.packages import get_licenses
from app.tasks.importtasks import apply_cdb_json
from ..factories import create_user, create_package, create_token, client_request


URL = "/api/packages/owner/pkg/"


def setup(state: PackageState = PackageState.APPROVED) -> tuple[Package, str]:
	owner = create_user("owner")
	package = create_package("pkg", owner, state=state)
	_, access_token = create_token(owner, package)
	return package, access_token


def put(client, access_token: str | None, data):
	headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
	return client_request(client, "PUT", URL, headers=headers, json=data)


def get_package() -> Package:
	db.session.expire_all()
	return Package.query.filter_by(name="pkg").one()


def test_edit_package(client):
	_, access_token = setup()

	rv = put(client, access_token, {
		"title": "New Title",
		"short_description": "New short",
		"long_description": "New long",
		"tags": ["mapgen"],
		"content_warnings": [],
		"licenses": ["GPLv3"],
		"website": "https://example.com",
		"dev_state": "BETA",
	})

	assert rv.status_code == 200, rv.json
	assert rv.json["success"] is True
	assert rv.json["was_modified"] is True
	assert rv.json["package"]["title"] == "New Title"
	package = get_package()
	assert (package.title, package.short_desc, package.desc) == ("New Title", "New short", "New long")
	assert [x.name for x in package.tags] == ["mapgen"]
	assert [x.name for x in package.licenses] == ["GPLv3"]
	assert package.website == "https://example.com"
	entry = AuditLogEntry.query.filter(AuditLogEntry.title.like("Edited New Title (API, token=test)%")).one()
	assert entry.package == package


def test_edit_package_unchanged(client):
	_, access_token = setup()

	rv = put(client, access_token, {"title": "pkg"})

	assert rv.status_code == 200
	assert rv.json["was_modified"] is False


def test_edit_package_ignores_read_only_fields(client):
	_, access_token = setup()

	rv = put(client, access_token, {"title": "New", "author": "someone", "downloads": 100, "state": "WIP"})

	assert rv.status_code == 200, rv.json
	package = get_package()
	assert package.author.username == "owner"
	assert package.downloads == 0
	assert package.state == PackageState.APPROVED


@pytest.mark.parametrize("data,status,error", [
	({"unknown_field": 1}, 400, "unknown_field is not a known field"),
	({"title": 5}, 400, "title must be a str"),
	({"title": None}, 400, "title must not be null"),
	({"website": "ftp://example.com"}, 400, "website must start with http:// or https://"),
	({"tags": ["not_a_tag"]}, 400, "Unknown tag: not_a_tag"),
	({"content_warnings": ["not_a_warning"]}, 400, "Unknown warning: not_a_warning"),
	({"licenses": ["Not a license"]}, 400, "Unknown license Not a license"),
	({"licenses": ["GPLv3", "Not a license"]}, 400, "Unknown license Not a license"),
	({"licenses": ["MIT%"]}, 400, "Unknown license MIT%"),
	({"licenses": []}, 400, "At least one license is required"),
	({"licenses": "GPLv3"}, 400, "licenses must be a list"),
	({"licenses": [1]}, 400, "licenses must be a list of license names"),
	({"licenses": None}, 400, "licenses must not be null"),
	({"license": "Not a license"}, 400, "Unknown license Not a license"),
	({"license": "GPLv3, MIT"}, 400, "Unknown license GPLv3, MIT"),
	({"media_license": ["GPLv3"]}, 400, "media_license must be a str"),
	({"short_description": "a", "short_desc": "b"}, 403, "Aliased field (short_description) does not match new field (short_desc)"),
	({"name": "renamed"}, 403, "You don't have permission to change the package name"),
	({"type": "GAME"}, 403, "You cannot change package type once approved"),
])
def test_edit_package_invalid(client, data, status, error):
	_, access_token = setup()

	rv = put(client, access_token, data)

	assert rv.status_code == status
	assert rv.json == {"success": False, "error": error}
	package = get_package()
	assert (package.title, package.name, package.license_names) == ("pkg", "pkg", "MIT")


@pytest.mark.parametrize("field,model", [("tags", Tag), ("content_warnings", ContentWarning)])
def test_edit_package_unknown_id(client, field, model):
	_, access_token = setup()
	missing_id = (db.session.query(db.func.max(model.id)).scalar() or 0) + 1000

	rv = put(client, access_token, {field: [missing_id]})

	assert rv.status_code == 400
	assert rv.json == {"success": False, "error": f"Unknown {'tag' if field == 'tags' else 'warning'}: {missing_id}"}
	assert getattr(get_package(), field) == []


def test_edit_package_tags_by_id(client):
	_, access_token = setup()
	tag = Tag.query.filter_by(name="mapgen").one()

	rv = put(client, access_token, {"tags": [tag.id]})

	assert rv.status_code == 200
	assert [x.name for x in get_package().tags] == ["mapgen"]


def test_rename_unapproved_package(client):
	_, access_token = setup(PackageState.WIP)

	rv = put(client, access_token, {"name": "renamed"})

	assert rv.status_code == 200, rv.json
	db.session.expire_all()
	assert [x.name for x in Package.query.all()] == ["renamed"]


def test_rename_unapproved_package_invalid(client):
	_, access_token = setup(PackageState.WIP)

	rv = put(client, access_token, {"name": "Bad Name"})

	assert rv.status_code == 400
	assert rv.json == {"success": False,
			"error": "Name can only contain lower case letters (a-z), digits (0-9), and underscores (_)"}


@pytest.mark.parametrize("value,expected", [
	(["GPLv3", "MIT"], ["GPLv3", "MIT"]),
	(["MIT", " gplv3 ", "mit"], ["GPLv3", "MIT"]),
	(["CC-BY-SA"], ["CC-BY-SA"]),
])
def test_edit_package_licenses(client, value, expected):
	_, access_token = setup()

	rv = put(client, access_token, {"licenses": value})

	assert rv.status_code == 200, rv.json
	data = rv.json["package"]
	assert (data["licenses"], data["license"], data["media_license"]) == (expected, None, None)
	assert [x.name for x in get_package().sorted_licenses] == expected


@pytest.mark.parametrize("data,expected", [
	({"license": "GPLv3", "media_license": "CC-BY-SA"}, "CC-BY-SA, GPLv3"),
	({"license": "GPLv3", "media_license": "GPLv3"}, "GPLv3"),
	({"license": "GPLv3"}, "MIT"),
	({"media_license": "cc-by-sa"}, "MIT"),
	({"license": "GPLv3", "media_license": None}, "MIT"),
	({"licenses": ["GPLv3", "CC-BY-SA"], "license": "gplv3", "media_license": "CC-BY-SA"}, "CC-BY-SA, GPLv3"),
	({"licenses": ["GPLv3"], "license": None}, "GPLv3"),
	({"license": None, "media_license": None}, "MIT"),
])
def test_edit_package_legacy_licenses(client, data, expected):
	_, access_token = setup()

	rv = put(client, access_token, data)

	assert rv.status_code == 200, rv.json
	assert get_package().license_names == expected


@pytest.mark.parametrize("data,error", [
	({"licenses": ["GPLv3"], "license": "MIT"}, "license (MIT) is not in licenses"),
	({"licenses": ["GPLv3"], "media_license": "CC-BY-SA"}, "media_license (CC-BY-SA) is not in licenses"),
])
def test_edit_package_legacy_licenses_mismatch(client, data, error):
	_, access_token = setup()

	rv = put(client, access_token, data)

	assert rv.status_code == 400
	assert rv.json == {"success": False, "error": error}
	assert get_package().license_names == "MIT"


def test_edit_package_licenses_read_back_unchanged(client):
	_, access_token = setup()
	assert put(client, access_token, {"licenses": ["MIT", "GPLv3"]}).status_code == 200

	data = client_request(client, "GET", URL).json
	assert data is not None
	rv = put(client, access_token, {key: data[key] for key in ["licenses", "license", "media_license"]})

	assert rv.status_code == 200, rv.json
	assert rv.json["was_modified"] is False


@pytest.mark.parametrize("data", [
	{"licenses": ["MIT", "GPLv3"]},
	{"license": "MIT", "media_license": "GPLv3"},
])
def test_cdb_json_licenses(client, data):
	package, _ = setup()

	apply_cdb_json(package, data)

	assert get_package().license_names == "GPLv3, MIT"


def test_cdb_json_lone_legacy_license_ignored(client):
	package, _ = setup()
	package.licenses = get_licenses(["GPLv3", "CC-BY-SA"])
	db.session.commit()

	apply_cdb_json(package, {"license": "MIT"})

	assert get_package().license_names == "CC-BY-SA, GPLv3"


def test_schema_licenses(client):
	rv = client_request(client, "GET", "/api/cdb_schema/")

	assert rv.json is not None
	assert "MIT" in rv.json["$defs"]["license"]["enum"]
	properties = rv.json["properties"]
	assert properties["licenses"]["items"] == {"$ref": "#/$defs/license"}
	assert properties["license"]["deprecated"] is True
	assert properties["media_license"]["deprecated"] is True
	assert properties["license"]["anyOf"] == [{"$ref": "#/$defs/license"}, {"type": "null"}]


def test_client_shows_licenses(client):
	_, access_token = setup()
	assert put(client, access_token, {"licenses": ["MIT", "GPLv3"]}).status_code == 200

	rv = client_request(client, "GET", URL + "for-client/?formspec_version=7")

	assert rv.json is not None
	assert "Licenses: <b>GPLv3, MIT</b>" in rv.json["info_hypertext"]["body"]


def test_edit_package_needs_token(client):
	setup()
	assert put(client, None, {"title": "New"}).status_code == 401
	assert get_package().title == "pkg"


def test_edit_package_token_for_other_package(client):
	package, _ = setup()
	other = create_package("other", package.author)
	_, access_token = create_token(package.author, other)

	rv = put(client, access_token, {"title": "New"})

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": "API token does not have access to the package"}
	assert get_package().title == "pkg"
