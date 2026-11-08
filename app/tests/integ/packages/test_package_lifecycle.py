# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Creating and editing packages, moving them through approval, removing them, and managing maintainers and aliases.
"""

import pytest

from app.models import db, User, UserRank, Package, PackageState, PackageType, PackageDevState, PackageAIDisclosure, \
	AuditLogEntry, AuditSeverity, Notification, License, PackageAlias, PackageScreenshot
from ..factories import create_user, create_package, create_release, create_screenshot, create_collection, \
	login_as, client_request


def get_package(name: str = "pkg") -> Package:
	db.session.expire_all()
	return Package.query.filter_by(name=name).one()


def as_user(client, username: str):
	login_as(client, User.query.filter_by(username=username).one())


def license_id(name: str = "MIT") -> str:
	return str(License.query.filter_by(name=name).one().id)


def package_form(**extra):
	return {
		"type": "MOD",
		"title": "My Package",
		"name": "pkg",
		"short_desc": "A package",
		"dev_state": "BETA",
		"ai_disclosure": "NONE",
		"license": license_id(),
		"media_license": license_id(),
		"desc": "Long description",
		**extra,
	}


def test_create_package(client):
	login_as(client, create_user("owner"))

	rv = client_request(client, "POST", "/packages/new/", data=package_form())

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/setup-releases/"
	package = get_package()
	assert package.author.username == "owner"
	assert [x.username for x in package.maintainers] == ["owner"]
	assert package.state == PackageState.WIP
	assert (package.title, package.short_desc, package.desc) == ("My Package", "A package", "Long description")
	assert package.dev_state == PackageDevState.BETA
	assert package.ai_disclosure == PackageAIDisclosure.NONE
	# Mods provide their own name
	assert [x.name for x in package.provides] == ["pkg"]
	assert AuditLogEntry.query.filter_by(title="Created package owner/pkg").count() == 1


def test_create_texture_pack_uses_media_license(client):
	login_as(client, create_user("owner"))

	client_request(client, "POST", "/packages/new/", data=package_form(type="TXP", license=license_id("GPLv3"),
			media_license=license_id("CC-BY-SA")))

	package = get_package()
	assert package.type == PackageType.TXP
	assert package.license.name == "CC-BY-SA"
	assert package.provides == []


@pytest.mark.parametrize("name,error", [
	("Bad Name", "Lower case letters (a-z), digits (0-9), and underscores (_) only"),
	("_game", "_game is not an allowed name"),
])
def test_create_package_invalid_name(client, name, error):
	login_as(client, create_user("owner"))

	rv = client_request(client, "POST", "/packages/new/", data=package_form(name=name))

	assert rv.status_code == 200
	assert error in rv.data.decode("utf-8")
	assert Package.query.count() == 0


def test_create_package_that_exists(client):
	owner = create_user("owner")
	create_package("pkg", owner)
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/new/", data=package_form())

	assert rv.status_code == 200
	assert "Package already exists" in rv.data.decode("utf-8")
	assert Package.query.count() == 1


def test_create_package_that_was_deleted(client):
	owner = create_user("owner")
	create_package("pkg", owner, state=PackageState.DELETED)
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/new/", data=package_form())

	assert rv.status_code == 302
	assert rv.headers["Location"].startswith("/report/?url=")
	assert get_package().state == PackageState.DELETED


def test_create_package_with_collection_name(client):
	owner = create_user("owner")
	create_collection(owner, name="pkg")
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/new/", data=package_form())

	assert rv.status_code == 200
	assert "A collection with a similar name already exists" in rv.data.decode("utf-8")
	assert Package.query.count() == 0


def test_create_package_needs_email(client):
	login_as(client, create_user("owner", email=None))

	rv = client_request(client, "POST", "/packages/new/", data=package_form())

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/settings/email/"
	assert Package.query.count() == 0


@pytest.mark.parametrize("rank,allowed", [
	(UserRank.TRUSTED_MEMBER, False),
	(UserRank.EDITOR, True),
])
def test_create_package_for_other_user(client, rank, allowed):
	create_user("other")
	login_as(client, create_user("staff", rank))

	rv = client_request(client, "POST", "/packages/new/?author=other", data=package_form())

	assert rv.status_code == 302
	if allowed:
		package = get_package()
		assert package.author.username == "other"
		assert [x.username for x in package.maintainers] == ["other"]
	else:
		assert rv.headers["Location"] == "/packages/new/"
		assert Package.query.count() == 0


def edit_form(package: Package, **extra):
	return package_form(**{
		"type": package.type.name,
		"title": package.title,
		"name": package.name,
		"short_desc": package.short_desc,
		"desc": package.desc,
		**extra,
	})


@pytest.mark.parametrize("username", ["owner", "maintainer", "editor"])
def test_edit_package(client, username):
	owner = create_user("owner")
	create_user("editor", UserRank.EDITOR)
	package = create_package("pkg", owner, maintainers=[create_user("maintainer")])
	as_user(client, username)

	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, title="New Title"))

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/"
	assert get_package().title == "New Title"
	entry = AuditLogEntry.query.filter(AuditLogEntry.title.like("Edited New Title%")).one()
	assert entry.causer.username == username
	assert entry.package.name == "pkg"


def test_edit_package_no_permission(client):
	package = create_package("pkg", create_user("owner"))
	login_as(client, create_user("approver", UserRank.APPROVER))

	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, title="New Title"))

	assert rv.status_code == 403
	assert get_package().title == "pkg"


@pytest.mark.parametrize("state,allowed", [
	(PackageState.WIP, True),
	(PackageState.APPROVED, False),
])
def test_rename_package(client, state, allowed):
	owner = create_user("owner")
	package = create_package("pkg", owner, state=state)
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, name="renamed"))

	db.session.expire_all()
	names = [x.name for x in Package.query.all()]
	if allowed:
		assert names == ["renamed"]
	else:
		assert rv.status_code == 200
		assert "You don&#39;t have permission to change the package name" in rv.data.decode("utf-8") or \
			"You don't have permission to change the package name" in rv.data.decode("utf-8")
		assert names == ["pkg"]


@pytest.mark.parametrize("state,allowed", [
	(PackageState.WIP, True),
	(PackageState.APPROVED, False),
])
def test_change_package_type(client, state, allowed):
	owner = create_user("owner")
	package = create_package("pkg", owner, state=state)
	login_as(client, owner)

	client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, type="GAME"))

	assert get_package().type == (PackageType.GAME if allowed else PackageType.MOD)


def make_ready(package: Package):
	"""
	Makes a package pass validate_package_for_approval.
	"""
	create_release(package, "1.0")
	create_screenshot(package, approved=False)
	package.ai_disclosure = PackageAIDisclosure.NONE
	package.supports_all_games = True
	db.session.commit()


def move(client, state: str):
	return client_request(client, "POST", f"/packages/owner/pkg/state/?state={state}")


@pytest.fixture
def lifecycle(client, eager_tasks, http_stub):
	owner = create_user("owner")
	create_user("maintainer")
	create_user("approver", UserRank.APPROVER)
	create_user("editor", UserRank.EDITOR)
	create_user("admin", UserRank.ADMIN)
	package = create_package("pkg", owner, state=PackageState.WIP,
			maintainers=[User.query.filter_by(username="maintainer").one()])
	make_ready(package)
	return package


def test_submit_and_approve(client, lifecycle):
	as_user(client, "owner")
	rv = move(client, "ready_for_review")
	assert rv.status_code == 302
	package = get_package()
	assert package.state == PackageState.READY_FOR_REVIEW
	assert AuditLogEntry.query.filter_by(title="Marked pkg as Ready for Review").count() == 1
	# Maintainers are notified, apart from whoever made the change
	notification = Notification.query.filter_by(title="Marked pkg as Ready for Review").one()
	assert notification.user.username == "maintainer"

	as_user(client, "approver")
	rv = move(client, "approved")
	assert rv.status_code == 302
	package = get_package()
	assert package.state == PackageState.APPROVED
	assert package.approved_at is not None
	# Screenshots are approved along with the package
	assert all(x.approved for x in PackageScreenshot.query.all())
	assert AuditLogEntry.query.filter_by(title="Approved pkg").count() == 1


def test_owner_cant_approve(client, lifecycle):
	lifecycle.state = PackageState.READY_FOR_REVIEW
	db.session.commit()
	as_user(client, "owner")

	rv = move(client, "approved")

	assert rv.status_code == 302
	assert get_package().state == PackageState.READY_FOR_REVIEW


def test_cant_skip_review(client, lifecycle):
	as_user(client, "admin")

	move(client, "approved")

	assert get_package().state == PackageState.WIP


def test_cant_submit_without_screenshot(client, lifecycle):
	PackageScreenshot.query.delete()
	db.session.commit()
	as_user(client, "owner")

	move(client, "ready_for_review")

	assert get_package().state == PackageState.WIP


def test_cant_submit_without_release(client, lifecycle):
	for release in lifecycle.releases.all():
		db.session.delete(release)
	db.session.commit()
	as_user(client, "owner")

	move(client, "ready_for_review")

	assert get_package().state == PackageState.WIP


def test_changes_needed(client, lifecycle):
	lifecycle.state = PackageState.READY_FOR_REVIEW
	db.session.commit()

	as_user(client, "owner")
	move(client, "changes_needed")
	assert get_package().state == PackageState.READY_FOR_REVIEW

	as_user(client, "approver")
	rv = move(client, "changes_needed")
	assert get_package().state == PackageState.CHANGES_NEEDED
	# There's no approval thread yet, so the approver is asked to start one
	assert rv.headers["Location"].startswith("/packages/owner/pkg/threads/new/")


@pytest.mark.parametrize("username,allowed", [
	("owner", True),
	("maintainer", True),
	("approver", False),
	# Editors can edit any package, but only maintainers and admins can move it back to draft
	("editor", False),
	("admin", True),
])
def test_back_to_draft(client, lifecycle, username, allowed):
	lifecycle.state = PackageState.READY_FOR_REVIEW
	db.session.commit()
	as_user(client, username)

	move(client, "wip")

	assert get_package().state == (PackageState.WIP if allowed else PackageState.READY_FOR_REVIEW)


def test_unknown_state(client, lifecycle):
	as_user(client, "owner")
	assert move(client, "published").status_code == 400


def test_approved_at_kept_on_reapproval(client, lifecycle):
	import datetime
	first = datetime.datetime(2020, 1, 1)
	lifecycle.state = PackageState.READY_FOR_REVIEW
	lifecycle.approved_at = first
	db.session.commit()
	as_user(client, "approver")

	move(client, "approved")

	package = get_package()
	assert package.state == PackageState.APPROVED
	assert package.approved_at == first


@pytest.fixture
def removable(client, eager_tasks, http_stub):
	owner = create_user("owner")
	create_user("editor", UserRank.EDITOR)
	create_user("approver", UserRank.APPROVER)
	create_user("stranger")
	return create_package("pkg", owner, maintainers=[create_user("maintainer")])


def remove(client, **form):
	return client_request(client, "POST", "/packages/owner/pkg/remove/", data=form)


@pytest.mark.parametrize("state", ["AS_IS", "DEPRECATED", "LOOKING_FOR_MAINTAINER"])
def test_set_dev_state(client, removable, state):
	as_user(client, "maintainer")

	rv = remove(client, **{state: "1"})

	assert rv.status_code == 302
	package = get_package()
	assert package.dev_state == PackageDevState[state]
	assert package.state == PackageState.APPROVED


@pytest.mark.parametrize("username,allowed", [
	("owner", True),
	("editor", True),
	("maintainer", False),
])
def test_delete_package(client, removable, username, allowed):
	as_user(client, username)

	rv = remove(client, delete="1", reason="Spam")

	assert rv.status_code == 302
	package = get_package()
	if allowed:
		assert package.state == PackageState.DELETED
		assert rv.headers["Location"] == "/users/owner/"
		entry = AuditLogEntry.query.filter_by(title="Deleted pkg, reason=Spam").one()
		assert entry.severity == AuditSeverity.EDITOR
	else:
		assert package.state == PackageState.APPROVED


@pytest.mark.parametrize("username,allowed", [
	("owner", True),
	("approver", False),
	("editor", True),
	("maintainer", False),
])
def test_unapprove_package(client, removable, username, allowed):
	as_user(client, username)

	rv = remove(client, unapprove="1", reason="Broken")

	package = get_package()
	if username == "approver":
		# Approvers have UNAPPROVE_PACKAGE, but can't open the remove page without EDIT_PACKAGE
		assert rv.status_code == 403
	if allowed:
		assert package.state == PackageState.WIP
		assert AuditLogEntry.query.filter_by(title="Unapproved pkg, reason=Broken").count() == 1
	else:
		assert package.state == PackageState.APPROVED


def test_remove_needs_permission(client, removable):
	as_user(client, "stranger")
	assert remove(client, delete="1").status_code == 403
	assert get_package().state == PackageState.APPROVED


@pytest.mark.parametrize("form", [{}, {"delete": "1", "reason": "x" * 501}])
def test_remove_bad_request(client, removable, form):
	as_user(client, "owner")
	assert remove(client, **form).status_code == 400
	assert get_package().state == PackageState.APPROVED


def maintainers() -> set[str]:
	return {x.username for x in get_package().maintainers}


@pytest.fixture
def maintained(client):
	owner = create_user("owner")
	create_user("editor", UserRank.EDITOR)
	create_user("alice")
	create_user("Bob")
	return create_package("pkg", owner, maintainers=[create_user("old")])


@pytest.mark.parametrize("username,severity", [
	("owner", AuditSeverity.NORMAL),
	("editor", AuditSeverity.MODERATION),
])
def test_edit_maintainers(client, maintained, username, severity):
	as_user(client, username)

	rv = client_request(client, "POST", "/packages/owner/pkg/edit-maintainers/",
			data={"maintainers_str": "alice, BOB, nobody"})

	assert rv.status_code == 302
	# Usernames are matched ignoring case, unknown ones are ignored, and the owner is always kept
	assert maintainers() == {"owner", "alice", "Bob"}
	assert AuditLogEntry.query.filter_by(title="Edited pkg maintainers").one().severity == severity
	assert Notification.query.filter_by(title="Added you as a maintainer of pkg").count() == 2
	assert Notification.query.filter_by(title="Removed you as a maintainer of pkg").one().user.username == "old"


def test_edit_maintainers_no_permission(client, maintained):
	as_user(client, "old")

	client_request(client, "POST", "/packages/owner/pkg/edit-maintainers/", data={"maintainers_str": "alice"})

	assert maintainers() == {"owner", "old"}


def test_remove_self_as_maintainer(client, maintained):
	as_user(client, "old")
	client_request(client, "POST", "/packages/owner/pkg/remove-self-maintainer/")
	assert maintainers() == {"owner"}
	assert AuditLogEntry.query.filter_by(title="Removed themself as a maintainer of pkg").count() == 1


def test_owner_cant_remove_self_as_maintainer(client, maintained):
	as_user(client, "owner")
	client_request(client, "POST", "/packages/owner/pkg/remove-self-maintainer/")
	assert maintainers() == {"owner", "old"}


@pytest.mark.parametrize("rank,status", [
	(UserRank.EDITOR, 403),
	(UserRank.ADMIN, 302),
])
def test_create_alias(client, rank, status):
	create_package("pkg", create_user("owner"))
	login_as(client, create_user("staff", rank))

	rv = client_request(client, "POST", "/packages/owner/pkg/aliases/new/",
			data={"author": "oldauthor", "name": "oldname"})

	assert rv.status_code == status
	aliases = [x.as_dict() for x in PackageAlias.query.all()]
	assert aliases == (["oldauthor/oldname"] if status == 302 else [])


def test_alias_redirects(client):
	package = create_package("pkg", create_user("owner"))
	alias = PackageAlias("oldauthor", "oldname")
	alias.package = package
	db.session.add(alias)
	db.session.commit()

	rv = client_request(client, "GET", "/packages/oldauthor/oldname/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/"

	rv = client_request(client, "GET", "/api/packages/oldauthor/oldname/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/api/packages/owner/pkg/"


def test_edit_alias_of_other_package(client):
	owner = create_user("owner")
	create_package("pkg", owner)
	other = create_package("other", owner)
	alias = PackageAlias("oldauthor", "oldname")
	alias.package = other
	db.session.add(alias)
	db.session.commit()
	login_as(client, create_user("admin", UserRank.ADMIN))

	rv = client_request(client, "POST", f"/packages/owner/pkg/aliases/{alias.id}/",
			data={"author": "x", "name": "y"})

	assert rv.status_code == 404


def test_game_name_redirect(client):
	create_package("mygame_game", create_user("owner"), type=PackageType.GAME)

	rv = client_request(client, "GET", "/packages/owner/mygame/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/mygame_game/"


@pytest.mark.parametrize("accept,status,location", [
	("application/zip", 204, None),
	("text/html", 302, "/packages/owner/pkg/"),
])
def test_download_without_release(client, accept, status, location):
	create_package("pkg", create_user("owner"))

	rv = client_request(client, "GET", "/packages/owner/pkg/download/", headers={"Accept": accept})

	assert rv.status_code == status
	assert rv.headers.get("Location") == location


def test_download_redirects_to_newest_approved_release(client):
	package = create_package("pkg", create_user("owner"))
	release = create_release(package, "1.0")
	create_release(package, "2.0", approved=False)

	rv = client_request(client, "GET", "/packages/owner/pkg/download/")

	assert rv.status_code == 302
	assert rv.headers["Location"] == f"/packages/owner/pkg/releases/{release.id}/download/"
