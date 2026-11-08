# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Creating, listing and deleting releases through the API.
"""

import io
import os

import pytest

from app import app
from app.domain.DomainError import DomainError
from app.domain.releases import check_can_create_release
from app.models import db, UserRank, PackageRelease, ReleaseState, AuditLogEntry, Package
from ..factories import create_user, create_package, create_release, create_token, client_request, make_mod_zip


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


@pytest.mark.parametrize("form,name,title", [
	({"name": "1.0"}, "1.0", "1.0"),
	({"title": "2.0"}, "2.0", "2.0"),
	({"name": "v3", "title": "Version three"}, "v3", "Version three"),
])
def test_release_name_and_title(client, eager_tasks, form, name, title):
	package, access_token = setup_package()

	rv = client_request(client, "POST", NEW_URL, headers=auth(access_token), content_type="multipart/form-data",
			data={"file": (io.BytesIO(make_mod_zip()), "pkg.zip"), **form})

	assert rv.status_code == 200, rv.json
	[release] = releases(package)
	assert (release.name, release.title) == (name, title)


@pytest.mark.parametrize("form,status,error", [
	({"name": "not a version"}, 403, "Release name must be in the form 1.2.3, v1.2.3, or 2025-02-01"),
	({"name": "1.0", "commit": "abc"}, 400, "Invalid commit hash; it must be a 40 character long base16 string"),
	({"name": "1.0", "commit": "g" * 40}, 400, "Invalid commit hash; it must be a 40 character long base16 string"),
])
def test_create_zip_release_invalid(client, form, status, error):
	package, access_token = setup_package()

	rv = client_request(client, "POST", NEW_URL, headers=auth(access_token), content_type="multipart/form-data",
			data={"file": (io.BytesIO(make_mod_zip()), "pkg.zip"), **form})

	assert rv.status_code == status
	assert rv.json == {"success": False, "error": error}
	assert releases(package) == []


@pytest.mark.parametrize("data,error", [
	({}, "name is required in the POST data"),
	({"name": "1.0"}, "Unknown release-creation method. Specify the method or provide a file."),
	({"name": "1.0", "method": "git"}, "ref is required in the POST data"),
])
def test_create_release_missing_fields(client, data, error):
	package, access_token = setup_package()

	rv = client_request(client, "POST", NEW_URL, headers=auth(access_token), json=data)

	assert rv.status_code == 400
	assert rv.json == {"success": False, "error": error}
	assert releases(package) == []


def test_create_release_not_a_zip(client):
	package, access_token = setup_package()

	rv = client_request(client, "POST", NEW_URL, headers=auth(access_token), content_type="multipart/form-data",
			data={"name": "1.0", "file": (io.BytesIO(make_mod_zip()), "pkg.tar.gz")})

	assert rv.status_code == 400
	assert rv.json == {"success": False, "error": "Please upload a zip file"}
	assert releases(package) == []


@pytest.mark.parametrize("existing_name,existing_title,error", [
	("1.0", "Other", "A release with this name already exists"),
	("0.9", "1.0", "A release with this title already exists"),
])
def test_create_release_duplicate(client, existing_name, existing_title, error):
	package, access_token = setup_package()
	existing = create_release(package, existing_name)
	existing.title = existing_title
	db.session.commit()

	rv = post_zip(client, access_token)

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": error}
	assert len(releases(package)) == 1


def test_create_release_needs_token(client):
	package, _ = setup_package()

	rv = post_zip(client, None)

	assert rv.status_code == 401
	assert releases(package) == []


def test_create_release_unknown_token(client):
	package, _ = setup_package()

	rv = post_zip(client, "x" * 32)

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": "Unknown API token"}
	assert releases(package) == []


def test_create_release_banned_owner(client):
	package, access_token = setup_package()
	package.author.rank = UserRank.BANNED
	db.session.commit()

	rv = post_zip(client, access_token)

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": "The API token's owner is banned"}
	assert releases(package) == []


def test_create_release_no_permission(client):
	package, _ = setup_package()
	_, access_token = create_token(create_user("stranger"))

	rv = post_zip(client, access_token)

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": "You do not have the permission to approve releases"}
	assert releases(package) == []


def test_create_release_token_for_other_package(client):
	package, _ = setup_package()
	other = create_package("other", package.author)
	_, access_token = create_token(package.author, other)

	rv = post_zip(client, access_token)

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": "API token does not have access to the package"}
	assert releases(package) == []


def test_check_can_create_release_needs_permission(client):
	"""
	The routes check permissions too, but the domain function mustn't rely on them.
	"""
	package, _ = setup_package()

	with pytest.raises(DomainError) as e:
		check_can_create_release(create_user("stranger"), package, "1.0", "1.0")

	assert e.value.code == 403
	assert e.value.message == "You don't have permission to make releases"


def test_maintainer_tokens_dont_work(client):
	"""
	API tokens only work on packages authored by the token's owner, so maintainers can't make releases through
	the API.
	"""
	owner = create_user("owner")
	maintainer = create_user("maintainer")
	package = create_package("pkg", owner, maintainers=[maintainer])
	_, access_token = create_token(maintainer)

	rv = post_zip(client, access_token)

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": "API token does not have access to the package"}
	assert releases(package) == []


def test_list_and_view_releases(client):
	package, _ = setup_package()
	old = create_release(package, "1.0")
	new = create_release(package, "2.0")

	rv = client_request(client, "GET", "/api/packages/owner/pkg/releases/")
	assert rv.status_code == 200
	assert rv.json is not None
	assert [x["id"] for x in rv.json] == [new.id, old.id]

	rv = client_request(client, "GET", f"/api/packages/owner/pkg/releases/{old.id}/")
	assert rv.status_code == 200
	assert rv.json == {
		"id": old.id,
		"name": "1.0",
		"title": "1.0",
		"release_notes": None,
		"url": old.upload_path,
		"release_date": old.created_at.isoformat(),
		"commit": None,
		"downloads": 0,
		"min_minetest_version": None,
		"max_minetest_version": None,
		"size": 0,
		"sha256": None,
	}

	other = create_package("other", package.author)
	other_release = create_release(other, "1.0")
	rv = client_request(client, "GET", f"/api/packages/owner/pkg/releases/{other_release.id}/")
	assert rv.status_code == 404


def test_list_releases_hides_unapproved(client):
	"""
	The list is public, so only shows releases that clients can install, like the website does for visitors.
	"""
	package, _ = setup_package()
	approved = create_release(package, "1.0")
	create_release(package, "2.0", approved=False)
	failed = create_release(package, "3.0", approved=False)
	failed.state = ReleaseState.FAILED
	processing = create_release(package, "4.0", approved=False)
	processing.state = ReleaseState.PROCESSING
	processing.task_id = "running"
	db.session.commit()

	rv = client_request(client, "GET", "/api/packages/owner/pkg/releases/")

	assert rv.status_code == 200
	assert rv.json is not None
	assert [x["id"] for x in rv.json] == [approved.id]


def test_delete_release(client):
	package, access_token = setup_package()
	old = create_release(package, "1.0")
	create_release(package, "2.0")
	local_path = os.path.join(app.config["UPLOAD_DIR"], os.path.basename(old.upload_path))
	with open(local_path, "wb") as f:
		f.write(make_mod_zip())

	rv = client_request(client, "DELETE", f"/api/packages/owner/pkg/releases/{old.id}/", headers=auth(access_token))

	assert rv.status_code == 200
	assert rv.json == {"success": True}
	assert [x.name for x in releases(package)] == ["2.0"]
	assert not os.path.exists(local_path)
	assert AuditLogEntry.query.filter_by(title="Deleted release 1.0 (API, token=test)").count() == 1


def test_delete_newest_release(client):
	package, access_token = setup_package()
	create_release(package, "1.0")
	newest = create_release(package, "2.0")

	rv = client_request(client, "DELETE", f"/api/packages/owner/pkg/releases/{newest.id}/", headers=auth(access_token))

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": "Unable to delete the release, make sure there's a newer release available"}
	assert len(releases(package)) == 2


@pytest.mark.parametrize("case", ["no-token", "stranger", "token-for-other-package", "other-package-release"])
def test_delete_release_denied(client, case):
	package, owner_token = setup_package()
	access_token: str | None = owner_token
	old = create_release(package, "1.0")
	create_release(package, "2.0")
	url = f"/api/packages/owner/pkg/releases/{old.id}/"
	expected = 403

	if case == "no-token":
		access_token = None
		expected = 401
	elif case == "stranger":
		stranger = create_user("stranger")
		create_package("theirs", stranger)
		_, access_token = create_token(stranger)
	elif case == "token-for-other-package":
		_, access_token = create_token(package.author, create_package("other", package.author))
	elif case == "other-package-release":
		other = create_package("other", package.author)
		other_release = create_release(other, "1.0")
		url = f"/api/packages/owner/pkg/releases/{other_release.id}/"
		expected = 404

	rv = client_request(client, "DELETE", url, headers=auth(access_token))

	assert rv.status_code == expected
	assert len(releases(package)) == 2
