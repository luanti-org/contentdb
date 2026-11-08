# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Creating, editing, deleting and downloading releases on the website.
"""

import io
import os

import pytest

from app import app, redis_client
from app.rediscache import make_download_key
from app.models import db, UserRank, PackageRelease, ReleaseState, AuditLogEntry, Package, LuantiRelease
from ..factories import create_user, create_package, create_release, login_as, client_request, make_mod_zip


def luanti(name: str) -> LuantiRelease:
	return LuantiRelease.query.filter_by(name=name).one()


def releases(package: Package) -> list[PackageRelease]:
	db.session.expire_all()
	return PackageRelease.query.filter_by(package_id=package.id).order_by(PackageRelease.id).all()


def create_form(**extra):
	return {
		"name": "1.0",
		"title": "",
		"release_notes": "",
		"upload_mode": "upload",
		"file_upload": (io.BytesIO(make_mod_zip()), "pkg.zip"),
		"min_rel": str(luanti("None").id),
		"max_rel": str(luanti("None").id),
		**extra,
	}


def write_upload(release: PackageRelease) -> str:
	path = os.path.join(app.config["UPLOAD_DIR"], os.path.basename(release.upload_path))
	with open(path, "wb") as f:
		f.write(make_mod_zip())
	return path


def test_create_release(client, eager_tasks):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/releases/new/", content_type="multipart/form-data",
			data=create_form(title="First", release_notes="Notes", min_rel=str(luanti("5.4").id)))

	[release] = releases(package)
	assert rv.status_code == 302
	assert rv.headers["Location"].startswith("/tasks/")
	assert f"r=/packages/owner/pkg/releases/{release.id}/edit/" in rv.headers["Location"].replace("%2F", "/")
	assert (release.name, release.title, release.release_notes) == ("1.0", "First", "Notes")
	assert release.min_rel == luanti("5.4")
	assert release.max_rel is None
	assert release.state == ReleaseState.APPROVED


def test_create_release_invalid_name(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/releases/new/", content_type="multipart/form-data",
			data=create_form(name="first release"))

	assert rv.status_code == 200
	assert "Release name must be in the form 1.2.3, v1.2.3, or 2025-02-01" in rv.data.decode("utf-8")
	assert releases(package) == []


def test_create_release_duplicate_shows_error(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	create_release(package, "1.0")
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/releases/new/", content_type="multipart/form-data",
			data=create_form())

	assert rv.status_code == 200
	assert "A release with this name already exists" in rv.data.decode("utf-8")
	assert len(releases(package)) == 1


def test_create_release_needs_email(client):
	owner = create_user("owner", email=None)
	package = create_package("pkg", owner)
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/releases/new/", content_type="multipart/form-data",
			data=create_form())

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/settings/email/"
	assert releases(package) == []


def test_create_release_no_permission(client):
	package = create_package("pkg", create_user("owner"))
	login_as(client, create_user("approver", UserRank.APPROVER))

	rv = client_request(client, "POST", "/packages/owner/pkg/releases/new/", content_type="multipart/form-data",
			data=create_form())

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/"
	assert releases(package) == []


def edit_form(release: PackageRelease, **extra):
	data = {
		"name": release.name,
		"title": release.title,
		"release_notes": release.release_notes or "",
		"min_rel": str(luanti("None").id),
		"max_rel": str(luanti("None").id),
	}
	if release.approved:
		data["approved"] = "y"
	data.update(extra)
	return {k: v for k, v in data.items() if v is not None}


def test_edit_release(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	release = create_release(package, "1.0")
	login_as(client, owner)

	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{release.id}/edit/",
			data=edit_form(release, title="New title", max_rel=str(luanti("5.5").id)))

	assert rv.status_code == 302
	[release] = releases(package)
	assert release.title == "New title"
	assert release.max_rel == luanti("5.5")
	assert release.approved
	assert AuditLogEntry.query.filter_by(title="Edited release New title").count() == 1


def test_owner_can_unapprove_and_reapprove(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	release = create_release(package, "1.0")
	login_as(client, owner)
	url = f"/packages/owner/pkg/releases/{release.id}/edit/"

	client_request(client, "POST", url, data=edit_form(release, approved=None))
	assert releases(package)[0].state == ReleaseState.UNAPPROVED
	assert AuditLogEntry.query.filter_by(title="Unapproved release 1.0").count() == 1

	client_request(client, "POST", url, data=edit_form(release, approved="y"))
	assert releases(package)[0].state == ReleaseState.APPROVED
	assert AuditLogEntry.query.filter_by(title="Approved release 1.0").count() == 1


def test_approver_can_only_change_approval(client):
	package = create_package("pkg", create_user("owner"))
	release = create_release(package, "1.0", approved=False)
	login_as(client, create_user("approver", UserRank.APPROVER))

	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{release.id}/edit/",
			data=edit_form(release, title="Changed by approver", approved="y"))

	assert rv.status_code == 302
	[release] = releases(package)
	assert release.title == "1.0"
	assert release.approved


@pytest.mark.parametrize("state", [ReleaseState.FAILED, ReleaseState.PROCESSING])
def test_cant_approve_failed_or_processing_release(client, state):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	release = create_release(package, "1.0", approved=False)
	release.state = state
	if state == ReleaseState.PROCESSING:
		release.task_id = "running"
	db.session.commit()
	login_as(client, owner)

	client_request(client, "POST", f"/packages/owner/pkg/releases/{release.id}/edit/",
			data=edit_form(release, approved="y"))

	assert releases(package)[0].state == state


def test_edit_release_no_permission(client):
	package = create_package("pkg", create_user("owner"))
	release = create_release(package, "1.0")
	login_as(client, create_user("stranger"))

	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{release.id}/edit/",
			data=edit_form(release, title="Hacked", approved=None))

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/"
	[release] = releases(package)
	assert release.title == "1.0"
	assert release.approved


def test_delete_release(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	old = create_release(package, "1.0")
	create_release(package, "2.0")
	path = write_upload(old)
	login_as(client, owner)

	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{old.id}/delete/")

	assert rv.status_code == 302
	assert [x.name for x in releases(package)] == ["2.0"]
	assert not os.path.exists(path)
	assert AuditLogEntry.query.filter_by(title="Deleted release 1.0").count() == 1


@pytest.mark.parametrize("username", ["owner", "stranger"])
def test_delete_release_denied(client, username):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	old = create_release(package, "1.0")
	newest = create_release(package, "2.0")
	login_as(client, owner if username == "owner" else create_user(username))

	# Owners can't delete the newest release, and strangers can't delete any
	target = newest if username == "owner" else old
	rv = client_request(client, "POST", f"/packages/owner/pkg/releases/{target.id}/delete/")

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/releases/"
	assert len(releases(package)) == 2


@pytest.mark.parametrize("only_change_none,expected_min", [
	(True, ["5.0", "5.4"]),
	(False, ["5.4", "5.4"]),
])
def test_bulk_change_releases(client, only_change_none, expected_min):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	with_min = create_release(package, "1.0")
	with_min.min_rel = luanti("5.0")
	create_release(package, "2.0")
	db.session.commit()
	login_as(client, owner)

	data = {
		"set_min": "y",
		"min_rel": str(luanti("5.4").id),
		"max_rel": str(luanti("5.5").id),
	}
	if only_change_none:
		data["only_change_none"] = "y"
	rv = client_request(client, "POST", "/packages/owner/pkg/releases/bulk_change/", data=data)

	assert rv.status_code == 302
	result = releases(package)
	assert [x.min_rel.name for x in result] == expected_min
	# set_max wasn't ticked
	assert [x.max_rel for x in result] == [None, None]
	assert AuditLogEntry.query.filter_by(title="Bulk changed Luanti versions of releases").count() == 1


def test_bulk_change_releases_no_permission(client):
	package = create_package("pkg", create_user("owner"))
	create_release(package, "1.0")
	login_as(client, create_user("stranger"))

	rv = client_request(client, "POST", "/packages/owner/pkg/releases/bulk_change/",
			data={"set_min": "y", "min_rel": str(luanti("5.4").id), "max_rel": str(luanti("5.5").id)})

	assert rv.status_code == 302
	assert releases(package)[0].min_rel is None


def package_counts(package: Package) -> tuple[int, float]:
	db.session.expire_all()
	reloaded = db.session.get(Package, package.id)
	assert reloaded is not None
	return reloaded.downloads, reloaded.score


@pytest.mark.parametrize("reason,bonus", [
	(None, 0),
	("new", 1),
	("dependency", 0.5),
	("update", 0.5),
])
def test_download_release(client, reason, bonus):
	package = create_package("pkg", create_user("owner"))
	release = create_release(package, "1.0")
	# The key is by package name, so would otherwise survive from other tests
	redis_client.delete(make_download_key("127.0.0.1", package))
	url = f"/packages/owner/pkg/releases/{release.id}/download/" + (f"?reason={reason}" if reason else "")
	headers = {"User-Agent": "Luanti/5.10.0 (Linux/6.0 x86_64)"}

	rv = client_request(client, "GET", url, headers=headers)
	assert rv.status_code == 302
	assert rv.headers["Location"] == release.upload_path
	assert package_counts(package) == (1, bonus)
	assert releases(package)[0].downloads == 1

	# Downloads from the same IP are only counted once
	client_request(client, "GET", url, headers=headers)
	assert package_counts(package) == (1, bonus)


def test_download_release_from_other_package(client):
	owner = create_user("owner")
	create_package("pkg", owner)
	other = create_package("other", owner)
	release = create_release(other, "1.0")

	rv = client_request(client, "GET", f"/packages/owner/pkg/releases/{release.id}/download/")
	assert rv.status_code == 404
