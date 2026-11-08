# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Permission tables for threads and replies. See permission_tables.py.

Banned users are left out: they're logged out by check_for_ban before reaching any page, and Thread doesn't
check bans itself.
"""

from typing import Any

import pytest

from app.models import db, UserRank, Permission, Thread, Package
from app.utils.models import get_system_user
from ..factories import create_user, create_package, create_thread, create_reply, create_review
from ..permission_tables import make_roles, assert_permissions


THREAD_ROLES = ["anonymous", "stranger", "author", "owner", "maintainer", "watcher",
		"approver", "editor", "moderator", "admin"]
EVERYONE = set(THREAD_ROLES)
STAFF_WHO_SEE_PRIVATE = {"approver", "editor", "moderator", "admin"}
INVOLVED = {"author", "owner", "maintainer", "watcher"}
MODERATORS = {"moderator", "admin"}


def make_thread_roles() -> tuple[Package, dict[str, Any]]:
	"""
	Creates a package owned by "owner" and maintained by "maintainer", plus the other roles. Use `add_thread` to
	create threads on it by "author" and watched by "watcher".
	"""
	roles = make_roles({
		"anonymous": None,
		"stranger": UserRank.MEMBER,
		"author": UserRank.MEMBER,
		"owner": UserRank.MEMBER,
		"maintainer": UserRank.MEMBER,
		"watcher": UserRank.MEMBER,
		"approver": UserRank.APPROVER,
		"editor": UserRank.EDITOR,
		"moderator": UserRank.MODERATOR,
		"admin": UserRank.ADMIN,
	})
	assert list(roles) == THREAD_ROLES
	package = create_package("pkg", roles["owner"], maintainers=[roles["maintainer"]])
	return package, roles


def add_thread(package: Package | None, roles: dict[str, Any], private: bool = False, locked: bool = False,
		author=None) -> Thread:
	thread = create_thread(author or roles["author"], package, private=private)
	thread.locked = locked
	thread.watchers.append(roles["watcher"])
	db.session.commit()
	return thread


@pytest.mark.parametrize("private,locked,can_see,can_comment", [
	(False, False, EVERYONE, EVERYONE - {"anonymous"}),
	(True, False, INVOLVED | STAFF_WHO_SEE_PRIVATE, INVOLVED | STAFF_WHO_SEE_PRIVATE),
	# Only moderators can comment on locked threads
	(False, True, EVERYONE, MODERATORS),
	(True, True, INVOLVED | STAFF_WHO_SEE_PRIVATE, MODERATORS),
])
def test_thread(client, private, locked, can_see, can_comment):
	package, roles = make_thread_roles()
	thread = add_thread(package, roles, private=private, locked=locked)

	assert_permissions(thread, roles, {
		Permission.SEE_THREAD: can_see,
		Permission.COMMENT_THREAD: can_comment,
		Permission.LOCK_THREAD: MODERATORS,
		Permission.SET_THREAD_PRIVATE: {"editor"} | MODERATORS,
		Permission.DELETE_THREAD: MODERATORS,
	})


def test_thread_without_package(client):
	_, roles = make_thread_roles()
	thread = add_thread(None, roles, private=True)

	assert_permissions(thread, roles, {
		Permission.SEE_THREAD: {"author", "watcher"} | STAFF_WHO_SEE_PRIVATE,
	})


def test_approval_thread_cant_change_privacy(client):
	package, roles = make_thread_roles()
	thread = add_thread(package, roles, private=True)
	package.review_thread = thread
	db.session.commit()

	assert_permissions(thread, roles, {
		Permission.SET_THREAD_PRIVATE: set(),
	})


def test_review_thread_cant_change_privacy(client):
	package, roles = make_thread_roles()
	review = create_review(roles["author"], package)
	review.thread.watchers.append(roles["watcher"])
	db.session.commit()

	assert_permissions(review.thread, roles, {
		Permission.SET_THREAD_PRIVATE: set(),
	})


def test_maintainers_can_delete_system_threads(client):
	package, roles = make_thread_roles()
	thread = add_thread(package, roles, author=get_system_user())

	assert_permissions(thread, roles, {
		Permission.DELETE_THREAD: {"owner", "maintainer"} | MODERATORS,
	})


REPLY_ROLES = ["anonymous", "stranger", "thread_author", "reply_author", "approver", "editor", "moderator", "admin"]


def make_reply_roles():
	roles = make_roles({
		"anonymous": None,
		"stranger": UserRank.MEMBER,
		"thread_author": UserRank.MEMBER,
		# The lowest rank that can edit their own replies
		"reply_author": UserRank.NEW_MEMBER,
		"approver": UserRank.APPROVER,
		"editor": UserRank.EDITOR,
		"moderator": UserRank.MODERATOR,
		"admin": UserRank.ADMIN,
	})
	assert list(roles) == REPLY_ROLES
	package = create_package("pkg", create_user("owner"))
	thread = create_thread(roles["thread_author"], package)
	reply = create_reply(thread, roles["reply_author"])
	return thread, reply, roles


def test_reply(client):
	thread, reply, roles = make_reply_roles()

	assert_permissions(reply, roles, {
		Permission.EDIT_REPLY: {"reply_author"} | MODERATORS,
		Permission.DELETE_REPLY: MODERATORS,
	}, "second reply")

	# The first reply is the thread's content, so is deleted by deleting the thread
	assert_permissions(thread.first_reply, roles, {
		Permission.EDIT_REPLY: {"thread_author"} | MODERATORS,
		Permission.DELETE_REPLY: set(),
	}, "first reply")


def test_reply_in_locked_thread(client):
	thread, reply, roles = make_reply_roles()
	thread.locked = True
	db.session.commit()

	# Nobody can edit replies in locked threads, not even moderators
	assert_permissions(reply, roles, {
		Permission.EDIT_REPLY: set(),
		Permission.DELETE_REPLY: MODERATORS,
	}, "second reply")

	assert_permissions(thread.first_reply, roles, {
		Permission.EDIT_REPLY: set(),
		Permission.DELETE_REPLY: set(),
	}, "first reply")
