# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime

from flask import url_for
from flask_babel import force_locale, gettext

from app.models import db, User, Package, PackageReview, PackageReviewVote, UserBan, Thread, ThreadReply, \
	UserRank, AuditSeverity, PendingUserDeletion, UserDeletionReason
from app.utils.flask import abs_url_for
from app.utils.models import get_system_user, add_audit_log, add_system_audit_log


DELETION_PERIODS = {
	UserDeletionReason.REQUESTED: datetime.timedelta(days=7),
	UserDeletionReason.INACTIVE: datetime.timedelta(days=30),
}

# How long before deletion the reminder email is sent
REMINDER_BEFORE = datetime.timedelta(days=1)


def delete_user(user: User):
	"""
	Deletes a user and the packages they authored, without committing.

	Model cascades remove the user's content, such as threads, replies, reviews, votes and collections, and everything
	belonging to their packages. Audit log entries and reports are kept, with the user or package set to NULL.
	Report threads and the user's comments in them are kept, and reassigned to the system user.
	"""
	# Reviews and packages whose stored scores depend on the user's votes and reviews
	voted_reviews = (PackageReview.query
			.filter(PackageReview.votes.any(PackageReviewVote.user_id == user.id),
				PackageReview.author_id != user.id,
				PackageReview.package.has(Package.author_id != user.id))
			.all())
	reviewed_packages = (Package.query
			.filter(Package.reviews.any(PackageReview.author_id == user.id), Package.author_id != user.id)
			.all())

	system_user = get_system_user()

	# Keep bans issued by the user, such as a former moderator. The ban is also recorded in the audit log.
	UserBan.query.filter_by(banned_by_id=user.id).update({"banned_by_id": system_user.id},
			synchronize_session="fetch")

	# Keep report threads for moderation. These are reassigned before deleting, so the cascades don't reach them.
	for thread in Thread.query.filter(Thread.author_id == user.id, Thread.report.any()).all():
		thread.author = system_user
	for reply in ThreadReply.query.filter(ThreadReply.author_id == user.id, ThreadReply.thread.has(Thread.report.any())).all():
		reply.author = system_user
	db.session.flush()

	db.session.delete(user)
	db.session.flush()

	for review in voted_reviews:
		db.session.expire(review, ["votes"])
		review.update_score()

	for package in reviewed_packages:
		package.recalculate_score()


def schedule_user_deletion(user: User, reason: UserDeletionReason):
	from app.utils.user import end_user_sessions

	if user.pending_deletion is None:
		user.pending_deletion = PendingUserDeletion()
	user.pending_deletion.reason = reason
	user.pending_deletion.created_at = datetime.datetime.utcnow()
	user.pending_deletion.delete_at = datetime.datetime.utcnow() + DELETION_PERIODS[reason]
	user.pending_deletion.reminder_sent_at = None

	end_user_sessions(user)

	if reason == UserDeletionReason.REQUESTED:
		add_audit_log(AuditSeverity.USER, user, "Requested account deletion",
				url_for("users.profile", username=user.username))
	else:
		add_system_audit_log(AuditSeverity.USER, f"Scheduled {user.username} for deletion as {reason.value}",
				url_for("users.profile", username=user.username))


def send_deletion_scheduled_email(user: User):
	pending = user.pending_deletion
	_send_deletion_email(user, _get_scheduled_email, pending.reason, pending.delete_at)


def cancel_user_deletion(user: User, causer: User) -> bool:
	if user.pending_deletion is None:
		return False

	user.pending_deletion = None
	add_audit_log(AuditSeverity.USER, causer, f"Cancelled deletion of {user.username}",
			url_for("users.profile", username=user.username))
	return True


def get_deletion_blocker(user: User) -> str | None:
	if user.packages.count() > 0:
		return "they own packages"
	elif user.is_banned:
		return "they are banned"
	elif user.rank.at_least(UserRank.MODERATOR):
		return "they are a moderator or above"
	return None


def get_pending_deletion_error(user: User) -> str | None:
	if user.pending_deletion is None:
		return None

	return gettext("%(username)s's account will be deleted on %(date)s, so this can't be done.",
			username=user.username, date=_format_date(user.pending_deletion.delete_at))


def send_deletion_reminder(user: User):
	pending = user.pending_deletion
	_send_deletion_email(user, _get_reminder_email, pending.reason, pending.delete_at)
	pending.reminder_sent_at = datetime.datetime.utcnow()


def process_pending_user_deletion(user_id: int) -> bool:
	pending = (PendingUserDeletion.query
			.filter(PendingUserDeletion.user_id == user_id,
				PendingUserDeletion.delete_at <= datetime.datetime.utcnow())
			.with_for_update()
			.populate_existing()
			.first())
	if pending is None:
		db.session.rollback()
		return False

	user = pending.user
	username = user.username
	blocker = get_deletion_blocker(user)
	if blocker:
		# Actions that cause blockers check get_pending_deletion_error, so this shouldn't happen. The user expects to
		# be deleted, so staff need to follow it up.
		user.pending_deletion = None
		add_system_audit_log(AuditSeverity.USER, f"Cancelled deletion of {username} as {blocker}",
				url_for("users.profile", username=username))
		db.session.commit()
		_alert_staff(f"Unable to delete {username} as {blocker}. Their deletion was cancelled, but they asked to be "
				f"deleted, so this needs following up: {abs_url_for('users.profile', username=username)}")
		return False

	email = user.email
	locale = user.locale or "en"
	reason = pending.reason

	add_system_audit_log(AuditSeverity.USER, f"Deleted user {username} ({reason.value})",
			url_for("users.profile", username=username))
	delete_user(user)
	db.session.commit()

	if email:
		with force_locale(locale):
			subject, text = _get_deleted_email(username, reason)
		_send_email(email, locale, subject, text)

	return True


def _alert_staff(message: str):
	import sentry_sdk
	from app.tasks.webhooktasks import post_discord_webhook

	sentry_sdk.capture_message(message, level="error")
	post_discord_webhook.delay(None, f"**Account deletion**\n{message}", True)


def _format_date(date: datetime.datetime) -> str:
	return date.strftime("%Y-%m-%d %H:%M UTC")


def _send_email(email: str, locale: str, subject: str, text: str):
	from app.tasks.emails import send_user_email
	send_user_email.delay(email, locale, subject, text)


def _send_deletion_email(user: User, get_email, reason: UserDeletionReason, delete_at: datetime.datetime):
	if not user.email:
		return

	locale = user.locale or "en"
	with force_locale(locale):
		subject, text = get_email(user.username, reason, delete_at)
	_send_email(user.email, locale, subject, text)


def _get_cancel_text(delete_at: datetime.datetime) -> str:
	return gettext("To keep your account, sign in before %(date)s: %(url)s",
			date=_format_date(delete_at), url=abs_url_for("users.login"))


def _get_scheduled_email(username: str, reason: UserDeletionReason, delete_at: datetime.datetime) -> tuple[str, str]:
	subject = gettext("Your ContentDB account will be deleted")
	if reason == UserDeletionReason.REQUESTED:
		intro = gettext("You asked for your ContentDB account %(username)s to be deleted. "
				"It will be deleted on %(date)s.", username=username, date=_format_date(delete_at))
	else:
		intro = gettext("Your ContentDB account %(username)s hasn't been used for a long time, "
				"so it will be deleted on %(date)s.", username=username, date=_format_date(delete_at))

	text = intro + "\n\n" + _get_cancel_text(delete_at)
	if reason == UserDeletionReason.REQUESTED:
		text += "\n\n" + gettext("If you didn't ask for this, sign in to cancel the deletion and then change your password.")
	return subject, text


def _get_reminder_email(username: str, reason: UserDeletionReason, delete_at: datetime.datetime) -> tuple[str, str]:
	subject = gettext("Your ContentDB account will be deleted tomorrow")
	text = gettext("Your ContentDB account %(username)s will be deleted on %(date)s.",
			username=username, date=_format_date(delete_at))
	text += "\n\n" + _get_cancel_text(delete_at)
	return subject, text


def _get_deleted_email(username: str, reason: UserDeletionReason) -> tuple[str, str]:
	subject = gettext("Your ContentDB account has been deleted")
	if reason == UserDeletionReason.REQUESTED:
		text = gettext("Your ContentDB account %(username)s has been deleted, as you asked.", username=username)
	else:
		text = gettext("Your ContentDB account %(username)s has been deleted, as it hadn't been used for a long time.",
				username=username)
	return subject, text
