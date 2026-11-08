# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Uploading screenshots through the website and the API.
"""

import io

import pytest

from app.models import db, UserRank, PackageState, PackageScreenshot, Package
from ..factories import create_user, create_package, create_token, login_as, client_request
from .test_uploads import make_image


UI_URL = "/packages/owner/pkg/screenshots/new/"
API_URL = "/api/packages/owner/pkg/screenshots/new/"


def screenshots(package: Package) -> list[PackageScreenshot]:
	db.session.expire_all()
	return PackageScreenshot.query.filter_by(package_id=package.id).all()


def post_ui(client, data: bytes, filename: str = "shot.png"):
	return client_request(client, "POST", UI_URL, content_type="multipart/form-data", data={
		"title": "My screenshot",
		"file_upload": (io.BytesIO(data), filename),
	})


def post_api(client, access_token: str | None, data: bytes, filename: str = "shot.png", **form):
	headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
	return client_request(client, "POST", API_URL, headers=headers, content_type="multipart/form-data", data={
		"title": "My screenshot",
		"file": (io.BytesIO(data), filename),
		**form,
	})


@pytest.mark.parametrize("user_rank,maintainer,state,approved", [
	# Screenshots by members on approved packages need approving
	(UserRank.MEMBER, True, PackageState.APPROVED, False),
	(UserRank.TRUSTED_MEMBER, True, PackageState.APPROVED, True),
	(UserRank.MEMBER, True, PackageState.WIP, True),
	(UserRank.EDITOR, False, PackageState.APPROVED, True),
])
def test_ui_create_screenshot(client, user_rank, maintainer, state, approved):
	owner = create_user("owner")
	user = create_user("user", user_rank)
	package = create_package("pkg", owner, state=state, maintainers=[user] if maintainer else [])
	login_as(client, user)

	rv = post_ui(client, make_image())

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/screenshots/"
	[ss] = screenshots(package)
	assert ss.title == "My screenshot"
	assert ss.approved == approved
	assert (ss.width, ss.height) == (1280, 720)
	assert ss.upload_path.startswith("/uploads/")


def test_ui_create_screenshot_no_permission(client):
	package = create_package("pkg", create_user("owner"))
	login_as(client, create_user("stranger", UserRank.APPROVER))

	rv = post_ui(client, make_image())

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/"
	assert screenshots(package) == []


def test_ui_create_screenshot_anonymous(client):
	package = create_package("pkg", create_user("owner"))

	rv = post_ui(client, make_image())

	assert rv.status_code == 302
	assert "/user/login/" in rv.headers["Location"]
	assert screenshots(package) == []


@pytest.mark.parametrize("data,filename,message", [
	(make_image(size=(800, 450)), "shot.png", "Screenshot is too small"),
	(b"<html><script>alert(1)</script></html>", "shot.png", "actually an image"),
	(make_image(), "shot.gif", "Please upload a PNG, JPEG, or WebP image file"),
], ids=["too-small", "not-an-image", "wrong-extension"])
def test_ui_create_screenshot_invalid(client, data, filename, message):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	login_as(client, owner)

	rv = post_ui(client, data, filename)

	assert rv.status_code == 200
	assert message in rv.data.decode("utf-8")
	assert screenshots(package) == []


def test_api_create_screenshot(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	_, access_token = create_token(owner, package)

	rv = post_api(client, access_token, make_image(), is_cover_image="yes")

	assert rv.status_code == 200, rv.json
	[ss] = screenshots(package)
	assert rv.json["screenshot"]["id"] == ss.id
	# Approval follows APPROVE_SCREENSHOT, which members don't have on approved packages
	assert not ss.approved
	assert package.cover_image == ss


def test_api_create_screenshot_trusted_is_approved(client):
	owner = create_user("owner", UserRank.TRUSTED_MEMBER)
	package = create_package("pkg", owner)
	_, access_token = create_token(owner, package)

	rv = post_api(client, access_token, make_image())

	assert rv.status_code == 200, rv.json
	[ss] = screenshots(package)
	assert ss.approved
	assert package.cover_image is None


def test_api_token_only_works_on_own_packages(client):
	"""
	Unlike the website, API tokens only work on packages that the token's owner authored, even for editors.
	"""
	package = create_package("pkg", create_user("owner"))
	_, access_token = create_token(create_user("editor", UserRank.EDITOR))

	rv = post_api(client, access_token, make_image())

	assert rv.status_code == 403
	assert rv.json["error"] == "API token does not have access to the package"
	assert screenshots(package) == []


def test_api_create_screenshot_needs_token(client):
	package = create_package("pkg", create_user("owner"))

	rv = post_api(client, None, make_image())

	assert rv.status_code == 401
	assert screenshots(package) == []


def test_api_create_screenshot_no_permission(client):
	package = create_package("pkg", create_user("owner"))
	_, access_token = create_token(create_user("stranger", UserRank.APPROVER))

	rv = post_api(client, access_token, make_image())

	assert rv.status_code == 403
	assert screenshots(package) == []


def test_api_create_screenshot_token_for_other_package(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	other = create_package("other", owner)
	_, access_token = create_token(owner, other)

	rv = post_api(client, access_token, make_image())

	assert rv.status_code == 403
	assert screenshots(package) == []


@pytest.mark.parametrize("data,filename,status", [
	(b"<html><script>alert(1)</script></html>", "shot.png", 400),
	(make_image(), "shot.svg", 400),
	# Too small is reported as 429, as it uses the same error as the rate limit
	(make_image(size=(800, 450)), "shot.png", 429),
], ids=["not-an-image", "wrong-extension", "too-small"])
def test_api_create_screenshot_invalid(client, data, filename, status):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	_, access_token = create_token(owner, package)

	rv = post_api(client, access_token, data, filename)

	assert rv.status_code == status
	assert rv.json["success"] is False
	assert screenshots(package) == []
