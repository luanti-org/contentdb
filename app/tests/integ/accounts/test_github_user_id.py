# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest

from app.models import db, Notification
from app.tasks import TaskError
from app.tasks.usertasks import update_github_user_id_raw
from ..factories import create_user, get_user


def test_sets_github_user_id(client, http_stub):
	user = create_user("member", github_user_id=None)
	user.github_username = "member-gh"
	db.session.commit()
	http_stub.add("GET", "https://api.github.com/users/member-gh", json={"id": 1234, "login": "member-gh"})

	assert update_github_user_id_raw(user) is True
	db.session.commit()

	assert get_user("member").github_user_id == 1234
	assert len(http_stub.calls) == 1


def test_disconnects_missing_github_account(client, http_stub):
	user = create_user("member")
	user.github_username = "deleted-gh"
	db.session.commit()
	http_stub.add("GET", "https://api.github.com/users/deleted-gh", status=404, json={"message": "Not Found"})

	assert update_github_user_id_raw(user, send_notif=True) is False
	db.session.commit()

	user = get_user("member")
	assert user.github_username is None
	notification = Notification.query.filter_by(user_id=user.id).one()
	assert "deleted-gh does not exist" in notification.title


def test_other_errors_keep_github_account(client, http_stub):
	user = create_user("member")
	user.github_username = "member-gh"
	db.session.commit()
	http_stub.add("GET", "https://api.github.com/users/member-gh", status=403, json={"message": "Rate limited"})

	assert update_github_user_id_raw(user, send_notif=True) is False
	db.session.commit()

	assert get_user("member").github_username == "member-gh"
	assert Notification.query.count() == 0


def test_rejects_non_int_id(client, http_stub):
	user = create_user("member")
	user.github_username = "member-gh"
	db.session.commit()
	http_stub.add("GET", "https://api.github.com/users/member-gh", json={"id": "1234"})

	with pytest.raises(TaskError):
		update_github_user_id_raw(user)
