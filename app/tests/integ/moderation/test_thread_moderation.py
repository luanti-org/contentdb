# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Moderating threads and replies: locking, privacy, deleting and editing. The permission rules themselves are in
test_thread_permission_tables.py; these check the routes use them and record what happened.
"""

import pytest

from app.models import db, User, UserRank, Thread, ThreadReply, AuditLogEntry, AuditSeverity, Notification
from app.utils.models import get_system_user
from ..factories import create_user, create_package, create_thread, create_reply, login_as, client_request


def setup_thread():
	owner = create_user("owner")
	author = create_user("author")
	watcher = create_user("watcher")
	create_user("member")
	create_user("editor", UserRank.EDITOR)
	create_user("moderator", UserRank.MODERATOR)
	package = create_package("pkg", owner)
	thread = create_thread(author, package, "Thread title", comment="Opening post")
	reply = create_reply(thread, watcher, "Second post")
	thread.watchers.append(watcher)
	db.session.commit()
	return thread, reply


def as_user(client, username: str):
	login_as(client, User.query.filter_by(username=username).one())


def audit_titles() -> list[str]:
	return [x.title for x in AuditLogEntry.query.order_by(AuditLogEntry.id).all()]


def reload_thread(thread_id: int) -> Thread | None:
	db.session.expire_all()
	return db.session.get(Thread, thread_id)


def get_thread(thread_id: int) -> Thread:
	thread = reload_thread(thread_id)
	assert thread is not None
	return thread


def get_reply(reply_id: int) -> ThreadReply:
	db.session.expire_all()
	reply = db.session.get(ThreadReply, reply_id)
	assert reply is not None
	return reply


@pytest.mark.parametrize("lock", [True, False])
def test_set_lock(client, lock):
	thread, _ = setup_thread()
	thread.locked = not lock
	db.session.commit()
	as_user(client, "moderator")

	rv = client_request(client, "POST", f"/threads/{thread.id}/set-lock/?lock={'yes' if lock else 'no'}")

	assert rv.status_code == 302
	thread = get_thread(thread.id)
	assert thread.locked == lock
	msg = f"{'Locked' if lock else 'Unlocked'} thread 'Thread title'"
	entry = AuditLogEntry.query.filter_by(title=msg).one()
	assert entry.severity == AuditSeverity.MODERATION
	assert entry.causer.username == "moderator"
	assert Notification.query.filter_by(title=msg).one().user.username == "watcher"


@pytest.mark.parametrize("username", ["author", "owner", "editor"])
def test_set_lock_no_permission(client, username):
	thread, _ = setup_thread()
	as_user(client, username)

	rv = client_request(client, "POST", f"/threads/{thread.id}/set-lock/?lock=yes")

	assert rv.status_code == 404
	assert not get_thread(thread.id).locked
	assert audit_titles() == []


@pytest.mark.parametrize("private", [True, False])
def test_set_private(client, private):
	thread, _ = setup_thread()
	thread.private = not private
	db.session.commit()
	as_user(client, "editor")

	rv = client_request(client, "POST", f"/threads/{thread.id}/set-private/?private={'yes' if private else 'no'}")

	assert rv.status_code == 302
	assert get_thread(thread.id).private == private
	msg = f"Made thread 'Thread title' {'private' if private else 'public'}"
	assert AuditLogEntry.query.filter_by(title=msg).one().severity == AuditSeverity.MODERATION


@pytest.mark.parametrize("username", ["author", "owner"])
def test_set_private_no_permission(client, username):
	thread, _ = setup_thread()
	as_user(client, username)

	rv = client_request(client, "POST", f"/threads/{thread.id}/set-private/?private=yes")

	assert rv.status_code == 404
	assert not get_thread(thread.id).private
	assert audit_titles() == []


def test_set_private_approval_thread(client):
	thread, _ = setup_thread()
	thread.package.review_thread = thread
	thread.private = True
	db.session.commit()
	as_user(client, "moderator")

	rv = client_request(client, "POST", f"/threads/{thread.id}/set-private/?private=no")

	assert rv.status_code == 404
	assert get_thread(thread.id).private


def test_delete_thread(client):
	thread, _ = setup_thread()
	thread_id = thread.id
	as_user(client, "moderator")

	rv = client_request(client, "GET", f"/threads/{thread_id}/delete/")
	assert rv.status_code == 200
	assert reload_thread(thread_id) is not None

	rv = client_request(client, "POST", f"/threads/{thread_id}/delete/")
	assert rv.status_code == 302
	assert reload_thread(thread_id) is None
	assert ThreadReply.query.filter_by(thread_id=thread_id).count() == 0

	entry = AuditLogEntry.query.filter_by(title="Deleted thread Thread title by author").one()
	assert entry.severity == AuditSeverity.MODERATION
	assert entry.package.name == "pkg"
	# The replies are kept in the audit log
	assert entry.description == "<author> Opening post\n\n<watcher> Second post"


@pytest.mark.parametrize("username", ["author", "owner", "editor"])
def test_delete_thread_no_permission(client, username):
	thread, _ = setup_thread()
	as_user(client, username)

	assert client_request(client, "GET", f"/threads/{thread.id}/delete/").status_code == 404
	assert client_request(client, "POST", f"/threads/{thread.id}/delete/").status_code == 404
	assert reload_thread(thread.id) is not None


def test_maintainer_can_delete_bot_thread(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	thread = create_thread(get_system_user(), package, "Messages for pkg")
	login_as(client, owner)

	rv = client_request(client, "POST", f"/threads/{thread.id}/delete/")

	assert rv.status_code == 302
	assert reload_thread(thread.id) is None


def test_delete_reply(client):
	thread, reply = setup_thread()
	reply_id = reply.id
	as_user(client, "moderator")

	rv = client_request(client, "GET", f"/threads/{thread.id}/delete-reply/?reply={reply_id}")
	assert rv.status_code == 200

	rv = client_request(client, "POST", f"/threads/{thread.id}/delete-reply/?reply={reply_id}")
	assert rv.status_code == 302
	db.session.expire_all()
	assert db.session.get(ThreadReply, reply_id) is None

	entry = AuditLogEntry.query.filter_by(title="Deleted reply by watcher").one()
	assert entry.severity == AuditSeverity.MODERATION
	assert entry.description == "Second post"


def test_delete_first_reply(client):
	thread, _ = setup_thread()
	first_id = thread.first_reply.id
	as_user(client, "moderator")

	rv = client_request(client, "POST", f"/threads/{thread.id}/delete-reply/?reply={first_id}")

	assert rv.status_code == 302
	db.session.expire_all()
	assert db.session.get(ThreadReply, first_id) is not None
	assert audit_titles() == []


@pytest.mark.parametrize("username", ["watcher", "owner", "editor"])
def test_delete_reply_no_permission(client, username):
	thread, reply = setup_thread()
	as_user(client, username)

	rv = client_request(client, "POST", f"/threads/{thread.id}/delete-reply/?reply={reply.id}")

	assert rv.status_code == 403
	db.session.expire_all()
	assert db.session.get(ThreadReply, reply.id) is not None


def test_delete_reply_from_other_thread(client):
	thread, reply = setup_thread()
	other = create_thread(create_user("other"), None, "Other thread")
	as_user(client, "moderator")

	assert client_request(client, "POST", f"/threads/{other.id}/delete-reply/?reply={reply.id}").status_code == 404
	assert client_request(client, "POST", f"/threads/{thread.id}/delete-reply/").status_code == 404
	db.session.expire_all()
	assert db.session.get(ThreadReply, reply.id) is not None


@pytest.mark.parametrize("username,severity", [
	("watcher", AuditSeverity.NORMAL),
	("moderator", AuditSeverity.MODERATION),
])
def test_edit_reply(client, username, severity):
	thread, reply = setup_thread()
	as_user(client, username)

	rv = client_request(client, "POST", f"/threads/{thread.id}/edit/?reply={reply.id}", data={"comment": "Edited post"})

	assert rv.status_code == 302
	assert get_reply(reply.id).comment == "Edited post"
	entry = AuditLogEntry.query.filter_by(title="Edited reply by watcher").one()
	assert entry.severity == severity
	# The old comment is kept in the audit log
	assert entry.description == "Second post"


@pytest.mark.parametrize("username,locked", [
	("author", False),
	("editor", False),
	("watcher", True),
	("moderator", True),
])
def test_edit_reply_no_permission(client, username, locked):
	thread, reply = setup_thread()
	thread.locked = locked
	db.session.commit()
	as_user(client, username)

	rv = client_request(client, "POST", f"/threads/{thread.id}/edit/?reply={reply.id}", data={"comment": "Edited post"})

	assert rv.status_code == 403
	assert get_reply(reply.id).comment == "Second post"
	assert audit_titles() == []
