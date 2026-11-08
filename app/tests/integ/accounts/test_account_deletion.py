# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
from unittest.mock import MagicMock

import pytest
from flask import g
from sqlalchemy import text

from app.domain import user_deletion
from app.models import db, User, UserRank, UserSession, PendingUserDeletion, UserDeletionReason, AuditLogEntry, APIToken, \
	UserBan, Thread, ThreadReply, Report, ReportCategory
from app.tasks import emails, webhooktasks, usertasks
from app.tasks.usertasks import process_pending_user_deletions
from app.utils.misc import hash_token, random_string
from app.utils.user import make_flask_login_password
from ..utils import login, is_logged_in, make_package


PASSWORD = "VYjNnjdDPhCVUZx"


@pytest.fixture
def send_user_email(monkeypatch):
	mock = MagicMock()
	monkeypatch.setattr(emails, "send_user_email", mock)
	return mock


@pytest.fixture
def staff_alerts(monkeypatch):
	discord = MagicMock()
	monkeypatch.setattr(webhooktasks, "post_discord_webhook", discord)
	sentry = MagicMock()
	monkeypatch.setattr("sentry_sdk.capture_message", sentry)
	return discord, sentry


def make_member(username: str = "member", email: str | None = "member@example.com") -> User:
	user = User(username, active=True, email=email, password=make_flask_login_password(PASSWORD))
	user.rank = UserRank.MEMBER
	db.session.add(user)
	db.session.commit()
	return user


def fresh_get(client, url):
	# The client fixture keeps one app context for the whole test, so Flask-Login's cached user in g would
	# otherwise survive between requests
	g.pop("_login_user", None)
	return client.get(url)


def fresh_login(client, username):
	g.pop("_login_user", None)
	return login(client, username, PASSWORD)


def request_deletion(client, username: str, confirm: str):
	g.pop("_login_user", None)
	return client.post(f"/users/{username}/delete/", data=dict(username=confirm), follow_redirects=True)


def get_pending(username: str) -> PendingUserDeletion | None:
	db.session.expire_all()
	return User.query.filter_by(username=username).one().pending_deletion


def must_get_pending(username: str) -> PendingUserDeletion:
	pending = get_pending(username)
	assert pending is not None
	return pending


def sent_subjects(mock: MagicMock) -> list[str]:
	return [call.args[2] for call in mock.delay.call_args_list]


def test_request_deletion(client, send_user_email):
	make_member()
	fresh_login(client, "member")

	rv = fresh_get(client, "/users/member/delete/")
	assert rv.status_code == 200
	assert b"Your account will be deleted after 7 days" in rv.data
	assert b"member@example.com" in rv.data

	rv = request_deletion(client, "member", "someone_else")
	assert b"Enter your username to confirm" in rv.data
	assert get_pending("member") is None
	send_user_email.delay.assert_not_called()

	before = datetime.datetime.utcnow()
	rv = request_deletion(client, "member", "MEMBER")
	assert b"Your account will be deleted on" in rv.data
	assert not is_logged_in(rv)

	pending = get_pending("member")
	assert pending is not None
	assert pending.reason == UserDeletionReason.REQUESTED
	assert before + datetime.timedelta(days=7) <= pending.delete_at <= \
			datetime.datetime.utcnow() + datetime.timedelta(days=7)
	assert pending.reminder_sent_at is None

	user = User.query.filter_by(username="member").one()
	assert UserSession.query.filter_by(user_id=user.id).count() == 0
	assert AuditLogEntry.query.filter_by(causer_id=user.id, title="Requested account deletion").count() == 1

	send_user_email.delay.assert_called_once()
	assert send_user_email.delay.call_args.args[0] == "member@example.com"
	assert sent_subjects(send_user_email) == ["Your ContentDB account will be deleted"]
	assert "/user/login/" in send_user_email.delay.call_args.args[3]


def test_request_deletion_without_email(client, send_user_email):
	make_member(email=None)
	fresh_login(client, "member")

	rv = fresh_get(client, "/users/member/delete/")
	assert b"have an email address, so we won" in rv.data

	request_deletion(client, "member", "member")
	assert get_pending("member") is not None
	send_user_email.delay.assert_not_called()


def test_package_owner_cannot_request_deletion(client, send_user_email):
	user = make_member()
	make_package("owned", user)
	db.session.commit()
	fresh_login(client, "member")

	rv = fresh_get(client, "/users/member/delete/")
	assert b"be deleted while you own packages" in rv.data
	assert b"Delete my account" not in rv.data

	request_deletion(client, "member", "member")
	assert get_pending("member") is None
	send_user_email.delay.assert_not_called()


def test_cannot_delete_other_users(client):
	make_member("victim")
	make_member("member", email="other@example.com")
	fresh_login(client, "member")

	assert fresh_get(client, "/users/victim/delete/").status_code == 403
	g.pop("_login_user", None)
	assert client.post("/users/victim/delete/", data=dict(username="victim")).status_code == 403
	assert get_pending("victim") is None


def test_admin_sees_admin_options(client):
	make_member()
	login(client, "rubenwardy", "tuckfrump")

	rv = fresh_get(client, "/users/member/delete/")
	assert rv.status_code == 200
	assert b"Deleting is permanent" in rv.data
	assert b'name="delete"' in rv.data


def test_logging_in_cancels_deletion(client, send_user_email):
	make_member()
	fresh_login(client, "member")
	request_deletion(client, "member", "member")
	assert get_pending("member") is not None

	rv = fresh_login(client, "member")
	assert is_logged_in(rv)
	assert b"Your account deletion has been cancelled" in rv.data
	assert get_pending("member") is None


def test_switch_user_does_not_cancel_deletion(client, send_user_email):
	make_member()
	fresh_login(client, "member")
	request_deletion(client, "member", "member")

	g.pop("_login_user", None)
	assert is_logged_in(login(client, "rubenwardy", "tuckfrump"))
	g.pop("_login_user", None)
	rv = client.post("/admin/switchuser/", data=dict(username="member"), follow_redirects=True)
	assert rv.status_code == 200
	assert get_pending("member") is not None


def schedule(username: str, delete_in: datetime.timedelta) -> int:
	user = User.query.filter_by(username=username).one()
	user.pending_deletion = PendingUserDeletion()
	user.pending_deletion.reason = UserDeletionReason.REQUESTED
	user.pending_deletion.delete_at = datetime.datetime.utcnow() + delete_in
	db.session.commit()
	return user.id


def test_reminder_is_sent_once_the_day_before(client, send_user_email):
	make_member()
	schedule("member", datetime.timedelta(days=3))

	process_pending_user_deletions()
	send_user_email.delay.assert_not_called()
	assert must_get_pending("member").reminder_sent_at is None

	must_get_pending("member").delete_at = datetime.datetime.utcnow() + datetime.timedelta(hours=20)
	db.session.commit()

	process_pending_user_deletions()
	assert sent_subjects(send_user_email) == ["Your ContentDB account will be deleted tomorrow"]
	assert must_get_pending("member").reminder_sent_at is not None

	process_pending_user_deletions()
	assert send_user_email.delay.call_count == 1
	assert User.query.filter_by(username="member").count() == 1


def test_due_deletion_deletes_user(client, send_user_email):
	make_member()
	user_id = schedule("member", -datetime.timedelta(minutes=1))

	process_pending_user_deletions()
	db.session.expire_all()

	assert User.query.get(user_id) is None
	assert PendingUserDeletion.query.count() == 0
	assert sent_subjects(send_user_email) == ["Your ContentDB account has been deleted"]
	assert send_user_email.delay.call_args.args[0] == "member@example.com"

	entry = AuditLogEntry.query.filter_by(title="Deleted user member (requested)").one()
	assert entry.url == "/users/member/"
	assert entry.causer.username == "ContentDB"


def test_due_deletion_is_cancelled_for_package_owner(client, send_user_email, staff_alerts):
	user = make_member()
	make_package("owned", user)
	db.session.commit()
	schedule("member", -datetime.timedelta(minutes=1))

	process_pending_user_deletions()

	assert User.query.filter_by(username="member").count() == 1
	assert get_pending("member") is None
	assert AuditLogEntry.query.filter_by(title="Cancelled deletion of member as they own packages").count() == 1
	send_user_email.delay.assert_not_called()

	# Staff are alerted, as the user expects to be deleted
	discord, sentry = staff_alerts
	sentry.assert_called_once()
	assert "Unable to delete member as they own packages" in sentry.call_args.args[0]
	discord.delay.assert_called_once()
	assert discord.delay.call_args.args[2] is True
	assert "Unable to delete member as they own packages" in discord.delay.call_args.args[1]


def test_expired_ban_does_not_block_deletion(client, send_user_email, staff_alerts):
	user = make_member()
	user_ban = UserBan()
	user_ban.banned_by = User.query.filter_by(username="rubenwardy").one()
	user_ban.message = "test"
	user_ban.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
	user.ban = user_ban
	db.session.commit()
	user_id = schedule("member", -datetime.timedelta(minutes=1))

	process_pending_user_deletions()
	db.session.expire_all()

	assert User.query.get(user_id) is None
	staff_alerts[1].assert_not_called()


def test_one_failed_deletion_does_not_stop_others(client, send_user_email, monkeypatch):
	make_member("broken", email="broken@example.com")
	make_member("member")
	broken_id = schedule("broken", -datetime.timedelta(minutes=2))
	member_id = schedule("member", -datetime.timedelta(minutes=1))

	real_delete_user = user_deletion.delete_user
	def delete_user(user):
		if user.username == "broken":
			raise Exception("Failed to delete")
		real_delete_user(user)
	monkeypatch.setattr(user_deletion, "delete_user", delete_user)
	capture_exception = MagicMock()
	monkeypatch.setattr("sentry_sdk.capture_exception", capture_exception)

	process_pending_user_deletions()
	db.session.expire_all()

	assert User.query.get(member_id) is None
	assert User.query.get(broken_id) is not None
	assert PendingUserDeletion.query.get(broken_id) is not None
	capture_exception.assert_called_once()


def test_deletion_cancelled_after_listing_is_not_processed(client, send_user_email, monkeypatch):
	# The task lists due users, then the user signs in, which cancels the deletion in another transaction
	make_member()
	user_id = schedule("member", -datetime.timedelta(minutes=1))

	real_process = usertasks.process_pending_user_deletion
	def process(due_user_id):
		with db.engine.begin() as conn:
			conn.execute(text("DELETE FROM pending_user_deletion WHERE user_id = :id"), {"id": due_user_id})
		return real_process(due_user_id)
	monkeypatch.setattr(usertasks, "process_pending_user_deletion", process)
	capture_exception = MagicMock()
	monkeypatch.setattr("sentry_sdk.capture_exception", capture_exception)

	process_pending_user_deletions()
	db.session.expire_all()

	assert User.query.get(user_id) is not None
	send_user_email.delay.assert_not_called()
	# The cancelled row is skipped, rather than failing on the stale row
	capture_exception.assert_not_called()


def test_scheduled_email_is_sent_after_commit(client, send_user_email, monkeypatch):
	make_member()
	fresh_login(client, "member")

	events = []
	send_user_email.delay.side_effect = lambda *args, **kwargs: events.append("email")

	real_commit = db.session.commit
	def commit():
		has_pending = PendingUserDeletion.query.count() > 0
		real_commit()
		if has_pending:
			events.append("committed")
	monkeypatch.setattr(db.session, "commit", commit)

	request_deletion(client, "member", "member")
	assert get_pending("member") is not None
	assert "email" in events
	assert events.index("committed") < events.index("email")


def test_actions_that_block_deletion_are_refused(client, send_user_email):
	make_member()
	other = make_member("other", email="other@example.com")
	make_package("other_mod", other)
	db.session.commit()
	schedule("member", datetime.timedelta(days=3))
	assert is_logged_in(login(client, "rubenwardy", "tuckfrump"))

	def post(url, data):
		g.pop("_login_user", None)
		return client.post(url, data=data, follow_redirects=True)

	rv = post("/admin/transfer/", dict(old_username="other", new_username="member", package="other_mod"))
	assert b"so this can" in rv.data
	assert User.query.filter_by(username="member").one().packages.count() == 0

	rv = post("/users/member/modtools/ban/", dict(message="test"))
	assert b"so this can" in rv.data
	db.session.expire_all()
	assert User.query.filter_by(username="member").one().ban is None

	for rank in ["MODERATOR", "BANNED"]:
		rv = post("/users/member/modtools/", dict(username="member", display_name="member", rank=rank))
		assert b"so this can" in rv.data
		db.session.expire_all()
		assert User.query.filter_by(username="member").one().rank == UserRank.MEMBER

	g.pop("_login_user", None)
	rv = client.get("/packages/new/?author=member", follow_redirects=True)
	assert b"so this can" in rv.data

	# Other rank changes are allowed
	post("/users/member/modtools/", dict(username="member", display_name="member", rank="TRUSTED_MEMBER"))
	db.session.expire_all()
	assert User.query.filter_by(username="member").one().rank == UserRank.TRUSTED_MEMBER
	assert get_pending("member") is not None


def test_deletion_page_counts_exclude_report_threads(client, send_user_email):
	user = make_member()
	thread = Thread()
	thread.title = "Report"
	thread.author = user
	db.session.add(thread)
	reply = ThreadReply()
	reply.thread = thread
	reply.author = user
	reply.comment = "Report"
	db.session.add(reply)
	report = Report()
	report.id = random_string(24)
	report.user = user
	report.thread = thread
	report.category = ReportCategory.SPAM
	report.title = "Spam"
	report.message = "Spam"
	db.session.add(report)
	db.session.commit()

	fresh_login(client, "member")
	rv = fresh_get(client, "/users/member/delete/")
	assert b"It removes 0 threads, 0 replies" in rv.data


def test_api_tokens_are_disabled_while_deletion_is_pending(client, send_user_email):
	user = make_member()
	token = APIToken()
	token.name = "test"
	token.owner = user
	access_token = random_string(32)
	token.access_token_hash = hash_token(access_token)
	db.session.add(token)
	db.session.commit()
	token_id = token.id

	def whoami():
		g.pop("_login_user", None)
		return client.get("/api/whoami/", headers={"Authorization": f"Bearer {access_token}"})

	def gitlab_push():
		return client.post("/gitlab/webhook/", headers={"X-Gitlab-Token": access_token}, json={
			"event_name": "push",
			"project": {"web_url": "https://github.com/example/example"},
			"ref": "refs/heads/main",
			"after": "0" * 40,
		})

	assert whoami().status_code == 200

	fresh_login(client, "member")
	request_deletion(client, "member", "member")
	assert get_pending("member") is not None

	rv = whoami()
	assert rv.status_code == 403
	assert rv.json["error"] == "The API token's owner's account is pending deletion"
	assert gitlab_push().status_code == 403

	# The token is kept, so it works again once the deletion is cancelled
	assert APIToken.query.get(token_id) is not None
	fresh_login(client, "member")
	assert get_pending("member") is None
	assert whoami().status_code == 200

	# It's deleted with the user
	g.pop("_login_user", None)
	user = User.query.filter_by(username="member").one()
	user.pending_deletion = PendingUserDeletion()
	user.pending_deletion.reason = UserDeletionReason.REQUESTED
	user.pending_deletion.delete_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
	db.session.commit()
	process_pending_user_deletions()
	db.session.expire_all()
	assert APIToken.query.get(token_id) is None
