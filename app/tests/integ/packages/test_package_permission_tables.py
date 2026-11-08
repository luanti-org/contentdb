# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Permission tables for packages, releases, reviews and collections. See permission_tables.py.
"""

import pytest

from app.models import db, PackageState, Permission, ReleaseState, UserRank
from ..factories import create_release, create_review, create_collection, create_package, create_user
from ..permission_tables import make_package_roles, assert_permissions, everyone_except, PACKAGE_ROLES, make_roles


MAINTAINERS = {"maintainer", "owner", "editor", "moderator", "admin"}
APPROVERS = {"approver", "editor", "moderator", "admin"}
LOGGED_IN_UNBANNED = everyone_except("anonymous", "banned")


def test_approved_package(client):
	package, roles = make_package_roles()
	assert package.approved

	assert_permissions(package, roles, {
		Permission.VIEW_PACKAGE: PACKAGE_ROLES,
		Permission.CREATE_THREAD: LOGGED_IN_UNBANNED,
		Permission.MAKE_RELEASE: MAINTAINERS,
		Permission.ADD_SCREENSHOTS: MAINTAINERS,
		Permission.EDIT_PACKAGE: MAINTAINERS,
		Permission.APPROVE_RELEASE: MAINTAINERS | APPROVERS,
		# The name can't change once approved, as it's part of the package's URL
		Permission.CHANGE_NAME: set(),
		Permission.APPROVE_NEW: APPROVERS,
		Permission.CHANGE_AUTHOR: APPROVERS,
		# Members' screenshots on approved packages need approving, so only trusted members and above can
		Permission.APPROVE_SCREENSHOT: APPROVERS,
		Permission.EDIT_MAINTAINERS: {"owner", "editor", "moderator", "admin"},
		Permission.DELETE_PACKAGE: {"owner", "editor", "moderator", "admin"},
		Permission.UNAPPROVE_PACKAGE: {"owner"} | APPROVERS,
	})


def test_unapproved_package(client):
	package, roles = make_package_roles(state=PackageState.READY_FOR_REVIEW)
	assert not package.approved

	assert_permissions(package, roles, {
		# Approvers can't view packages awaiting review, as VIEW_PACKAGE falls back to EDIT_PACKAGE
		Permission.VIEW_PACKAGE: MAINTAINERS,
		Permission.CREATE_THREAD: LOGGED_IN_UNBANNED,
		Permission.MAKE_RELEASE: MAINTAINERS,
		Permission.EDIT_PACKAGE: MAINTAINERS,
		Permission.CHANGE_NAME: MAINTAINERS,
		Permission.APPROVE_NEW: APPROVERS,
		Permission.APPROVE_SCREENSHOT: MAINTAINERS | APPROVERS,
		Permission.EDIT_MAINTAINERS: {"owner", "editor", "moderator", "admin"},
		Permission.DELETE_PACKAGE: {"owner", "editor", "moderator", "admin"},
	})


def test_release_permissions(client):
	package, roles = make_package_roles()
	old = create_release(package, "1.0")
	newest = create_release(package, "2.0")

	assert_permissions(old, roles, {
		Permission.DELETE_RELEASE: MAINTAINERS,
		Permission.APPROVE_RELEASE: MAINTAINERS | APPROVERS,
	}, "older release")

	# The newest release of an approved package can only be deleted by admins, so it always has a release
	assert_permissions(newest, roles, {
		Permission.DELETE_RELEASE: {"admin"},
	}, "newest release")

	newest.task_id = "processing"
	newest.state = ReleaseState.PROCESSING
	db.session.commit()
	assert_permissions(newest, roles, {
		Permission.DELETE_RELEASE: MAINTAINERS,
	}, "newest release, still processing")

	newest.task_id = None
	newest.state = ReleaseState.APPROVED
	package.state = PackageState.WIP
	db.session.commit()
	assert_permissions(newest, roles, {
		Permission.DELETE_RELEASE: MAINTAINERS,
	}, "newest release of unapproved package")


@pytest.mark.parametrize("approved,can_see", [
	(True, {"anonymous", "stranger", "reviewer", "owner", "approver", "editor", "moderator", "admin"}),
	# Unapproved reviews are held for moderation, and may be spam
	(False, {"reviewer", "moderator", "admin"}),
])
def test_review(client, approved, can_see):
	roles = make_roles({
		"anonymous": None,
		"stranger": UserRank.MEMBER,
		"reviewer": UserRank.MEMBER,
		"owner": UserRank.MEMBER,
		"approver": UserRank.APPROVER,
		"editor": UserRank.EDITOR,
		"moderator": UserRank.MODERATOR,
		"admin": UserRank.ADMIN,
	})
	package = create_package("pkg", roles["owner"])
	review = create_review(roles["reviewer"], package, approved=approved)

	assert_permissions(review, roles, {
		Permission.SEE_REVIEW: can_see,
		Permission.DELETE_REVIEW: {"reviewer", "moderator", "admin"},
		Permission.APPROVE_REVIEW: {"moderator", "admin"},
	})


@pytest.mark.parametrize("private,can_view,can_edit", [
	(False, {"anonymous", "stranger", "author", "approver", "editor", "moderator", "admin"},
			{"author", "editor", "moderator", "admin"}),
	# Editors can edit public collections, but can't see private ones
	(True, {"author", "moderator", "admin"}, {"author", "moderator", "admin"}),
])
def test_collection(client, private, can_view, can_edit):
	roles = make_roles({
		"anonymous": None,
		"stranger": UserRank.MEMBER,
		"author": UserRank.NEW_MEMBER,
		"approver": UserRank.APPROVER,
		"editor": UserRank.EDITOR,
		"moderator": UserRank.MODERATOR,
		"admin": UserRank.ADMIN,
	})
	package = create_package("pkg", create_user("owner"))
	collection = create_collection(roles["author"], [package], private=private)

	assert_permissions(collection, roles, {
		Permission.VIEW_COLLECTION: can_view,
		Permission.EDIT_COLLECTION: can_edit,
	})
