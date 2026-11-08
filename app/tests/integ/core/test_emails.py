# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from app.models import db, EmailSubscription
from app.tasks.emails import send_user_email


def test_user_email_is_sent(client, eager_tasks, mailpit):
	send_user_email.delay("member@example.com", "en", "Test subject", "Test body text")

	message = mailpit.wait_for("member@example.com")
	assert message["Subject"] == "Test subject"
	assert "Test body text" in mailpit.get_text(message)
	assert "You are receiving this email because you are a registered user of ContentDB." in mailpit.get_html(message)


def test_unsubscribed_address_is_skipped(client, eager_tasks, mailpit):
	sub = EmailSubscription("blocked@example.com")
	sub.blacklisted = True
	db.session.add(sub)
	db.session.commit()

	send_user_email.delay("blocked@example.com", "en", "Test subject", "Test body text")
	send_user_email.delay("member@example.com", "en", "Other subject", "Other body text")

	# The second email arriving shows the first was handled
	mailpit.wait_for("member@example.com")
	assert mailpit.messages_to("blocked@example.com") == []
