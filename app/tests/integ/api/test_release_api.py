# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Creating, listing and deleting releases through the API.
"""

import io
import os

from app.models import db, PackageRelease, ReleaseState, AuditLogEntry, Package
from ..factories import create_user, create_package, create_token, client_request, make_mod_zip


NEW_URL = "/api/packages/owner/pkg/releases/new/"


def setup_package(**kwargs) -> tuple[Package, str]:
	owner = create_user("owner", **kwargs)
	package = create_package("pkg", owner)
	_, access_token = create_token(owner, package)
	return package, access_token


def auth(access_token: str | None) -> dict[str, str]:
	return {"Authorization": f"Bearer {access_token}"} if access_token else {}


def post_zip(client, access_token: str | None, data: bytes | None = None, **form):
	return client_request(client, "POST", NEW_URL, headers=auth(access_token), content_type="multipart/form-data",
			data={"name": "1.0", "file": (io.BytesIO(data or make_mod_zip()), "pkg.zip"), **form})


def releases(package: Package) -> list[PackageRelease]:
	db.session.expire_all()
	return PackageRelease.query.filter_by(package_id=package.id).order_by(PackageRelease.id).all()


def test_create_zip_release(client, eager_tasks):
	package, access_token = setup_package()

	rv = post_zip(client, access_token, title="First release", release_notes="Notes",
			commit="ABCDEF0123456789ABCDEF0123456789ABCDEF01")

	assert rv.status_code == 200, rv.json
	[release] = releases(package)
	assert set(rv.json) == {"success", "task", "release"}
	assert rv.json["success"] is True
	assert rv.json["task"].startswith("/tasks/")
	assert rv.json["release"]["id"] == release.id
	assert rv.json["release"]["name"] == "1.0"
	assert rv.json["release"]["title"] == "First release"

	assert release.name == "1.0"
	assert release.title == "First release"
	assert release.release_notes == "Notes"
	assert release.commit_hash == "abcdef0123456789abcdef0123456789abcdef01"
	# The zip was checked by check_zip_release, which approved it
	assert release.state == ReleaseState.APPROVED
	assert release.task_id is None
	assert release.file_size_bytes > 0
	assert os.path.isfile(release.file_path)

	entry = AuditLogEntry.query.filter(AuditLogEntry.title.like("Created release%")).one()
	assert entry.title == "Created release First release (API, token=test)"
	assert entry.package == package
