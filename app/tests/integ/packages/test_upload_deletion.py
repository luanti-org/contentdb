# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Deleting a release or screenshot deletes its file from storage, by its upload path.

With Bunny storage, `file_path` is a copy in a local cache, such as /tmp/contentdb-uploads/abc.zip. Deleting by that
path asked Bunny to delete /tmp/contentdb-uploads/abc.zip, which failed with a 404 after the release was deleted.
"""

import os

import pytest
import requests

import app.uploads
from app import app as flask_app
from app.models import db, PackageRelease, PackageScreenshot
from ..factories import create_user, create_package, create_release, create_screenshot, create_token, login_as, \
	client_request, make_mod_zip


@pytest.fixture
def deleted(monkeypatch) -> list[str]:
	"""
	Records the paths that the storage backend is asked to delete
	"""
	calls: list[str] = []
	monkeypatch.setattr(app.uploads, "backend_delete_upload", lambda path: calls.append(path))
	return calls


def write_upload(upload_path: str):
	with open(os.path.join(flask_app.config["UPLOAD_DIR"], os.path.basename(upload_path)), "wb") as f:
		f.write(make_mod_zip())


def setup_releases():
	owner = create_user("owner")
	package = create_package("pkg", owner)
	old = create_release(package, "1.0")
	create_release(package, "2.0")
	write_upload(old.upload_path)
	return owner, package, old


def auth(owner, package):
	_, access_token = create_token(owner, package)
	return {"Authorization": f"Bearer {access_token}"}


def test_ui_release_deletion_deletes_by_upload_path(client, deleted):
	owner, package, old = setup_releases()
	upload_path = old.upload_path
	login_as(client, owner)

	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{old.id}/delete/")

	assert rv.status_code == 302
	assert deleted == [upload_path]


def test_api_release_deletion_deletes_by_upload_path(client, deleted):
	owner, package, old = setup_releases()
	upload_path = old.upload_path

	rv = client_request(client, "DELETE", f"/api/packages/owner/pkg/releases/{old.id}/", headers=auth(owner, package))

	assert rv.status_code == 200
	assert deleted == [upload_path]


def test_api_screenshot_deletion_deletes_by_upload_path(client, deleted):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	screenshot = create_screenshot(package)
	upload_path = screenshot.upload_path
	write_upload(upload_path)

	rv = client_request(client, "DELETE", f"/api/packages/owner/pkg/screenshots/{screenshot.id}/",
			headers=auth(owner, package))

	assert rv.status_code == 200
	assert deleted == [upload_path]
	assert PackageScreenshot.query.get(screenshot.id) is None


def test_storage_failure_doesnt_fail_the_request(client, monkeypatch):
	def fail(path):
		raise requests.HTTPError("404 Client Error: Not Found")

	monkeypatch.setattr(app.uploads, "backend_delete_upload", fail)
	owner, package, old = setup_releases()
	old_id = old.id
	login_as(client, owner)

	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{old_id}/delete/")

	assert rv.status_code == 302
	db.session.expire_all()
	assert PackageRelease.query.get(old_id) is None


def test_external_release_url_isnt_deleted(client, deleted):
	owner, package, old = setup_releases()
	old.upload_path = "https://github.com/example/mod/archive/master.zip"
	db.session.commit()
	login_as(client, owner)

	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{old.id}/delete/")

	assert rv.status_code == 302
	assert deleted == []
