# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Notification emails, sent immediately or as a daily digest depending on the user's preferences, and the
verification emails. They're sent to the test stack's Mailpit.
"""

import pytest

from app import app
from app.models import db, User, Notification, NotificationType, UserNotificationPreferences, EmailSubscription
from app.tasks.emails import send_pending_notifications, send_pending_digests, send_verify_email, \
	send_unsubscribe_verify
from ..factories import create_user


def make_user(username: str, email: str | None = None, prefs: dict[str, int] | None = None) -> User:
	user = create_user(username, email=email or f"{username}@example.com")
	preferences = UserNotificationPreferences(user)
	for key, value in (prefs or {}).items():
		setattr(preferences, "pref_" + key, value)
	db.session.add(preferences)
	db.session.commit()
	return user


def notify(user: User, title: str, type: NotificationType = NotificationType.THREAD_REPLY,
		url: str = "/threads/1/") -> Notification:
	causer = User.query.filter_by(username="causer").first() or create_user("causer")
	notification = Notification(user, causer, type, title, url)
	db.session.add(notification)
	db.session.commit()
	return notification


def run(task):
	result = task.apply()
	assert result.successful(), result.traceback


def emailed(title: str) -> bool:
	db.session.expire_all()
	return Notification.query.filter_by(title=title).one().emailed


def test_immediate_email(client, mailpit):
	user = make_user("member")
	notify(user, "New reply on your thread")

	run(send_pending_notifications)

	[message] = mailpit.messages_to("member@example.com")
	assert message["Subject"] == "New reply on your thread"
	text = mailpit.get_text(message)
	assert app.config["BASE_URL"] + "/threads/1/" in text
	assert "/users/member/settings/email/" in text or "Manage email settings" in text
	assert "/unsubscribe/" in text
	assert emailed("New reply on your thread")


def test_several_immediate_notifications_are_combined(client, mailpit):
	user = make_user("member")
	notify(user, "First reply", url="/threads/1/")
	notify(user, "Second reply", url="/threads/2/")

	run(send_pending_notifications)

	[message] = mailpit.messages_to("member@example.com")
	assert message["Subject"] == "2 new notifications"
	text = mailpit.get_text(message)
	assert "<causer> First reply" in text
	assert "<causer> Second reply" in text


def test_digest_only_notifications_wait_for_digest(client, mailpit):
	user = make_user("member")
	# New reviews default to the daily digest
	notify(user, "New review", NotificationType.NEW_REVIEW)

	run(send_pending_notifications)
	assert mailpit.messages_to("member@example.com") == []
	assert not emailed("New review")

	run(send_pending_digests)
	[message] = mailpit.messages_to("member@example.com")
	assert message["Subject"] == "1 new notifications"
	assert "<causer> New review" in mailpit.get_text(message)
	assert emailed("New review")

	# Only sent once
	mailpit.clear()
	run(send_pending_digests)
	assert mailpit.messages_to("member@example.com") == []


def test_disabled_notifications_are_never_emailed(client, mailpit):
	user = make_user("member", prefs={"other": 0})
	notify(user, "Something else", NotificationType.OTHER)

	run(send_pending_notifications)
	run(send_pending_digests)

	assert mailpit.messages_to("member@example.com") == []
	# Marked as handled, so it isn't checked again
	assert emailed("Something else")


@pytest.mark.parametrize("case", ["no-email", "no-preferences", "unsubscribed"])
def test_notifications_not_emailed(client, mailpit, case):
	if case == "no-email":
		user = make_user("member")
		user.email = None
	elif case == "no-preferences":
		user = create_user("member")
		assert user.notification_preferences is None
	elif case == "unsubscribed":
		user = make_user("member")
		sub = EmailSubscription("member@example.com")
		sub.blacklisted = True
		db.session.add(sub)
	db.session.commit()
	notify(user, "New reply on your thread")
	notify(user, "New review", NotificationType.NEW_REVIEW)

	run(send_pending_notifications)
	run(send_pending_digests)

	assert mailpit.messages_to("member@example.com") == []


def test_only_each_users_notifications(client, mailpit):
	alice = make_user("alice")
	bob = make_user("bob")
	carol = make_user("carol")
	notify(alice, "For alice")
	notify(bob, "For bob")

	run(send_pending_notifications)

	[to_alice] = mailpit.messages_to("alice@example.com")
	[to_bob] = mailpit.messages_to("bob@example.com")
	assert to_alice["Subject"] == "For alice"
	assert to_bob["Subject"] == "For bob"
	assert "For bob" not in mailpit.get_text(to_alice)
	assert mailpit.messages_to("carol@example.com") == []
	assert carol.notifications.count() == 0


def test_verify_email(client, mailpit):
	send_verify_email.apply(args=["new@example.com", "secrettoken", "en"])

	[message] = mailpit.messages_to("new@example.com")
	assert message["Subject"] == "Confirm email address"
	assert app.config["BASE_URL"] + "/user/verify/?token=secrettoken" in mailpit.get_text(message)


def test_verify_email_skips_unsubscribed(client, mailpit):
	sub = EmailSubscription("blocked@example.com")
	sub.blacklisted = True
	db.session.add(sub)
	db.session.commit()

	send_verify_email.apply(args=["blocked@example.com", "secrettoken", "en"])

	assert mailpit.messages_to("blocked@example.com") == []


def test_unsubscribe_verify(client, mailpit):
	send_unsubscribe_verify.apply(args=["member@example.com", "en"])

	[message] = mailpit.messages_to("member@example.com")
	assert message["Subject"] == "Confirm unsubscribe"
	sub = EmailSubscription.query_by_email("member@example.com").one()
	assert sub.url in mailpit.get_text(message)
