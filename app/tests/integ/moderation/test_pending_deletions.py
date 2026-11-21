# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime

import pytest
from bs4 import BeautifulSoup

from app.models import db, User, UserRank, PendingUserDeletion, UserDeletionReason
from ..factories import client_request, create_package, create_user, login_as


URL = "/admin/users/pending-deletion/"


def schedule(user: User, delete_in: datetime.timedelta, reason=UserDeletionReason.REQUESTED,
		reminder_sent: bool = False):
	now = datetime.datetime.utcnow()
	user.pending_deletion = PendingUserDeletion()
	user.pending_deletion.reason = reason
	user.pending_deletion.delete_at = now + delete_in
	user.pending_deletion.reminder_sent_at = now if reminder_sent else None
	db.session.commit()


def get_rows(client) -> dict[str, BeautifulSoup]:
	rv = client_request(client, "GET", URL)
	assert rv.status_code == 200
	soup = BeautifulSoup(rv.data.decode("utf-8"), "html.parser")
	return {row["data-username"]: row for row in soup.select(".pending-deletion")}  # type: ignore[misc]


@pytest.mark.parametrize("rank, allowed", [
	(None, False),
	(UserRank.MEMBER, False),
	(UserRank.EDITOR, False),
	(UserRank.APPROVER, False),
	(UserRank.MODERATOR, True),
	(UserRank.ADMIN, True),
])
def test_permissions(client, rank, allowed):
	if rank is not None:
		login_as(client, create_user("viewer", rank))

	rv = client_request(client, "GET", URL)
	if allowed:
		assert rv.status_code == 200
	else:
		assert rv.status_code != 200
		assert b"Scheduled user deletions" not in rv.data


def test_lists_only_scheduled_users_soonest_first(client):
	login_as(client, create_user("mod", UserRank.MODERATOR))
	create_user("not_scheduled")
	schedule(create_user("later"), datetime.timedelta(days=6))
	schedule(create_user("sooner"), datetime.timedelta(hours=5), reason=UserDeletionReason.INACTIVE,
			reminder_sent=True)

	rv = client_request(client, "GET", URL)
	assert b"2 scheduled." in rv.data

	rows = get_rows(client)
	assert list(rows.keys()) == ["sooner", "later"]

	sooner = rows["sooner"].get_text(" ", strip=True)
	assert "inactive" in sooner
	assert "No email" not in sooner
	assert "Overdue" not in sooner
	assert " No " not in f" {sooner} "

	later = rows["later"].get_text(" ", strip=True)
	assert "requested" in later
	assert " No " in f" {later} "


def test_empty(client):
	login_as(client, create_user("mod", UserRank.MODERATOR))

	rv = client_request(client, "GET", URL)
	assert rv.status_code == 200
	assert b"0 scheduled." in rv.data


def test_flags_overdue_blocked_and_no_email(client):
	login_as(client, create_user("mod", UserRank.MODERATOR))

	overdue = create_user("overdue", email=None)
	schedule(overdue, -datetime.timedelta(hours=2))

	blocked = create_user("blocked")
	create_package("SomeMod", blocked)
	schedule(blocked, datetime.timedelta(days=2))

	rows = get_rows(client)

	overdue_text = rows["overdue"].get_text(" ", strip=True)
	assert "Overdue" in overdue_text
	assert "No email" in overdue_text
	assert "Can't be deleted" not in overdue_text

	blocked_text = rows["blocked"].get_text(" ", strip=True)
	assert "Overdue" not in blocked_text
	assert "Can't be deleted, as they own packages" in blocked_text


def test_linked_from_admin_tools(client):
	login_as(client, create_user("mod", UserRank.MODERATOR))

	rv = client_request(client, "GET", "/admin/")
	assert rv.status_code == 200
	assert URL.encode() in rv.data


def test_not_linked_for_editors(client):
	login_as(client, create_user("editor", UserRank.EDITOR))

	rv = client_request(client, "GET", "/admin/")
	assert rv.status_code == 200
	assert URL.encode() not in rv.data
