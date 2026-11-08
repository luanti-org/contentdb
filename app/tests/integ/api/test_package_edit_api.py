# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Editing packages through the API, with PUT /api/packages/<author>/<name>/.
"""

import pytest

from app.models import db, Package, PackageState, PackageType, AuditLogEntry, Tag, ContentWarning
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
		"license": "GPLv3",
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
	assert package.license.name == "GPLv3"
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
	({"license": "Not a license"}, 400, "Unknown license Not a license"),
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
	assert (package.title, package.name) == ("pkg", "pkg")


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


def test_texture_pack_license_follows_media_license(client):
	package, access_token = setup()
	package.type = PackageType.TXP
	db.session.commit()

	rv = put(client, access_token, {"license": "GPLv3", "media_license": "CC-BY-SA"})

	assert rv.status_code == 200, rv.json
	package = get_package()
	assert (package.license.name, package.media_license.name) == ("CC-BY-SA", "CC-BY-SA")


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
