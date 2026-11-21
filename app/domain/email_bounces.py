# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Tracks email addresses that can't be delivered to, using delivery failures reported by Scaleway TEM.

Bounced addresses aren't sent emails, other than verification emails that the user asks for. Confirming the address
with a verification email clears the bounce.
"""

import datetime
import sys
from dataclasses import dataclass

from flask import url_for

from app.models import db, EmailSubscription, User, AuditSeverity, sql_hash_email
from app.utils import scaleway_tem
from app.utils.models import add_system_audit_log


# Flags on a failed email that mean the address shouldn't be sent to again, most specific first.
# Failures with only soft flags, such as soft_bounce, mailbox_full or greylisted, are ignored.
BOUNCE_FLAGS = ["mailbox_not_found", "hard_bounce", "blocklisted", "spam"]

# Automatic blocklist types that mean the address doesn't exist. `mailbox_full` is temporary, so is ignored.
BOUNCE_BLOCKLIST_TYPES = {"mailbox_not_found"}

# TEM retries soft bounces for up to 72 hours, and filters emails by when they were created. Each import looks back
# this much further than the last one, so emails that failed after a later import started aren't missed.
RETRY_WINDOW = datetime.timedelta(days=4)


@dataclass
class BounceImportResult:
	failed_emails: int = 0
	blocklists: int = 0
	newly_bounced: int = 0
	ignored: int = 0


def get_bounce_reason(email: dict) -> str | None:
	"""
	Returns a short reason if the failed `email` means the address shouldn't be sent to, otherwise None
	"""
	flags = set(email.get("flags") or [])
	flag = next((x for x in BOUNCE_FLAGS if x in flags), None)
	if flag is None:
		return None

	tries = email.get("last_tries") or []
	last_try = max(tries, key=lambda x: x.get("rank") or 0) if tries else None
	code = last_try and last_try.get("code")
	return f"{flag} ({code})" if code else flag


def get_email_bounce(email: str | None) -> EmailSubscription | None:
	"""
	Returns the subscription for `email` if it has bounced, without creating one
	"""
	if not email:
		return None

	return EmailSubscription.query_by_email(email).filter(EmailSubscription.bounced_at.is_not(None)).first()


def record_bounce(email: str, reason: str, sent_at: datetime.datetime | None) -> bool:
	"""
	Marks `email` as bounced, without committing. Returns True if it wasn't already.

	Failures of emails sent before the address was last confirmed to work are ignored, as they're out of date.
	"""
	sub = EmailSubscription.query_by_email(email).first()
	if sub is None:
		sub = EmailSubscription(email)
		db.session.add(sub)

	if sub.bounced_at is not None:
		return False

	if sub.bounce_cleared_at is not None and (sent_at is None or sent_at <= sub.bounce_cleared_at):
		return False

	sub.bounced_at = datetime.datetime.utcnow()
	sub.bounce_reason = reason[:100]

	for user in User.query.filter(User.email.is_not(None), sql_hash_email(User.email) == sub.email_hash).all():
		add_system_audit_log(AuditSeverity.USER, f"Email to {user.username} can't be delivered: {sub.bounce_reason}",
				url_for("users.profile", username=user.username))

	return True


def clear_bounce(email: str) -> bool:
	"""
	Records that `email` has been confirmed to work, without committing. Returns True if it had bounced.
	"""
	sub = EmailSubscription.query_by_email(email).first()
	if sub is None:
		return False

	was_bounced = sub.bounced_at is not None
	sub.bounced_at = None
	sub.bounce_reason = None
	sub.bounce_cleared_at = datetime.datetime.utcnow()
	return was_bounced


def import_bounces(since: datetime.datetime) -> BounceImportResult:
	"""
	Reads delivery failures from Scaleway TEM for emails created after `since`, and records bounces. Commits.

	Raises ScalewayTEMError if the API fails, after committing what was already read.
	"""
	result = BounceImportResult()

	try:
		for email in scaleway_tem.list_failed_emails(since):
			result.failed_emails += 1

			address = email.get("mail_rcpt") or email.get("rcpt_to")
			reason = get_bounce_reason(email)
			if not address or reason is None:
				result.ignored += 1
				continue

			if record_bounce(address, reason, scaleway_tem.parse_datetime(email.get("created_at"))):
				result.newly_bounced += 1

		if scaleway_tem.is_blocklist_configured():
			now = datetime.datetime.utcnow()
			for blocklist in scaleway_tem.list_blocklists():
				result.blocklists += 1

				ends_at = scaleway_tem.parse_datetime(blocklist.get("ends_at"))
				if blocklist.get("custom") or blocklist.get("type") not in BOUNCE_BLOCKLIST_TYPES or \
						not blocklist.get("email") or (ends_at is not None and ends_at <= now):
					result.ignored += 1
					continue

				if record_bounce(blocklist["email"], f"blocklist: {blocklist['type']}",
						scaleway_tem.parse_datetime(blocklist.get("created_at"))):
					result.newly_bounced += 1
	finally:
		db.session.commit()

	print(f"Read {result.failed_emails} failed emails and {result.blocklists} blocklists since {since}: "
			f"{result.newly_bounced} newly bounced, {result.ignored} ignored", file=sys.stderr)
	return result
