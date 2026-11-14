# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


import datetime
import requests
import sentry_sdk
import os
import sys

from flask import url_for
from sqlalchemy import or_, and_

from app import app
from app.models import User, db, UserRank, Thread, Package, Notification, NotificationType, UserSession, \
	AuditLogEntry, AuditSeverity, PendingUserDeletion
from app.utils.misc import random_string
from app.utils.models import create_session, add_notification, get_system_user, add_system_audit_log
from app.domain.user_deletion import delete_user, REMINDER_BEFORE, send_deletion_reminder, process_pending_user_deletion
from app.tasks import celery, TaskError
from app.utils.files import get_temp_dir
from app.uploads import copy_to_uploads, get_public_upload_url


@celery.task()
def delete_inactive_users():
	threshold = datetime.datetime.now() - datetime.timedelta(hours=5)

	# Users that only maintain packages are kept, such as ones created by importing a database dump
	users = User.query.filter(User.is_active == False, User.packages == None, User.forum_topics == None,
			~User.maintained_packages.any(), User.created_at <= threshold, User.rank == UserRank.NOT_JOINED).all()
	for user in users:
		delete_user(user)

	db.session.commit()


def get_unused_users_without_email_query():
	one_year_ago = datetime.datetime.utcnow() - datetime.timedelta(days=365)

	return User.query.filter(
		User.email.is_(None),
		User.rank.in_([UserRank.NOT_JOINED, UserRank.NEW_MEMBER, UserRank.MEMBER, UserRank.TRUSTED_MEMBER]),
		or_(User.created_at.is_(None), User.created_at < one_year_ago),
		~User.packages.any(),
		~User.maintained_packages.any(),
		~User.reviews.any(),
		~User.replies.any(),
		~User.threads.any(),
		~User.collections.any(),
		~User.tokens.any(),
		~User.audit_log_entries.any(AuditLogEntry.created_at >= one_year_ago),
		~User.audit_log_entries.any(AuditLogEntry.title.like("Granted \"%\" to OAuth2 application %")),

		# Deleting the user would cascade to these
		~User.forum_topics.any(),
		~User.clients.any(),
		~User.reports.any(),

		# Logged-in sessions don't create audit log entries
		~User.sessions.any(),

		# Keep bans, so that the username isn't freed up
		User.ban == None)


@celery.task()
def delete_unused_users_without_email():
	users = get_unused_users_without_email_query().all()
	for user in users:
		add_system_audit_log(AuditSeverity.MODERATION, f"Deleted unused user {user.username}",
				url_for("users.profile", username=user.username))
		delete_user(user)

	db.session.commit()

	print(f"Deleted {len(users)} unused users without an email", file=sys.stderr)
	return len(users)


@celery.task()
def process_pending_user_deletions():
	now = datetime.datetime.utcnow()

	reminders = PendingUserDeletion.query.filter(
			PendingUserDeletion.reminder_sent_at.is_(None),
			PendingUserDeletion.delete_at <= now + REMINDER_BEFORE,
			PendingUserDeletion.delete_at > now).all()
	for pending in reminders:
		send_deletion_reminder(pending.user)
		db.session.commit()

	due_ids = [x.user_id for x in PendingUserDeletion.query.filter(PendingUserDeletion.delete_at <= now).all()]
	deleted = 0
	failed = 0
	for user_id in due_ids:
		# One failure shouldn't stop the others. The row is left in place, so it's retried on the next run.
		try:
			if process_pending_user_deletion(user_id):
				deleted += 1
		except Exception as e:
			db.session.rollback()
			sentry_sdk.capture_exception(e)
			print(f"Failed to delete user {user_id}: {e}", file=sys.stderr)
			failed += 1

	print(f"Sent {len(reminders)} deletion reminders, deleted {deleted} of {len(due_ids)} due users, "
			f"{failed} failed", file=sys.stderr)


@celery.task()
def upgrade_new_members():
	with create_session() as session:
		threshold = datetime.datetime.now() - datetime.timedelta(days=7)

		session.query(User).filter(and_(User.rank == UserRank.NEW_MEMBER, or_(
				User.threads.any(Thread.created_at < threshold),
				User.packages.any(Package.approved_at < threshold)))).update({"rank": UserRank.MEMBER}, synchronize_session=False)

		session.commit()


@celery.task()
def set_profile_picture_from_url(username: str, url: str):
	print("### Setting pp for " + username + " to " + url, file=sys.stderr)
	user = User.query.filter_by(username=username).first()
	if user is None:
		raise TaskError(f"Unable to find user {username}")

	headers = {"Accept": "image/jpeg, image/png, image/webp"}
	resp = requests.get(url, stream=True, headers=headers, timeout=15)
	if resp.status_code != 200:
		raise TaskError(f"Failed to download {url}: {resp.status_code}: {resp.reason}")

	content_type = resp.headers["content-type"]
	if content_type is None:
		raise TaskError("Content-Type needed")
	elif content_type == "image/jpeg":
		ext = "jpg"
	elif content_type == "image/png":
		ext = "png"
	elif content_type == "image/webp":
		ext = "webp"
	else:
		raise TaskError(f"Unacceptable content-type: {content_type}")

	with get_temp_dir() as tmp_dir:
		filename = random_string(10) + "." + ext
		filepath = os.path.join(tmp_dir, filename)
		with open(filepath, "wb") as f:
			size = 0
			for chunk in resp.iter_content(chunk_size=1024):
				if chunk:  # filter out keep-alive new chunks
					size += len(chunk)
					if size > 3 * 1000 * 1000:  # 3 MB
						raise TaskError(f"File too large to download {url}")

					f.write(chunk)

		url = copy_to_uploads(filepath)
		user.profile_pic = get_public_upload_url(url)

	db.session.commit()

	return filepath


def update_github_user_id_raw(user: User, send_notif: bool = False):
	github_api_token = app.config.get("GITHUB_API_TOKEN")

	url = f"https://api.github.com/users/{user.github_username}"
	headers = {"Authorization": "token " + github_api_token} if github_api_token else None
	resp = requests.get(url, headers=headers, timeout=15)
	if resp.status_code == 404:
		print(" - not found", file=sys.stderr)
		if send_notif:
			system_user = get_system_user()
			add_notification(user, system_user, NotificationType.BOT,
					f"GitHub account {user.github_username} does not exist, so has been disconnected from your account",
					url_for("users.profile", username=user.username), None)
		user.github_username = None
		return False
	elif resp.status_code != 200:
		print(" - " + resp.json()["message"], file=sys.stderr)
		return False

	json = resp.json()
	user_id = json.get("id")
	if type(user_id) is not int:
		raise TaskError(f"{url} returned non-int id")

	user.github_user_id = user_id
	return True


@celery.task()
def update_github_user_id(user_id: int, github_username: str):
	user = User.query.get(user_id)
	if user is None:
		raise TaskError("Unable to find that user")

	user.github_username = github_username
	if update_github_user_id_raw(user):
		db.session.commit()
	else:
		raise TaskError(f"Unable to set the GitHub username to {github_username}")


@celery.task()
def import_github_user_ids():
	users = User.query.filter(User.github_user_id.is_(None), User.github_username.is_not(None)).all()
	total = len(users)
	count = 0
	for i, user in enumerate(users):
		print(f"[{i + 1} / {total}] Getting GitHub user id for {user.github_username}", file=sys.stderr)
		if update_github_user_id_raw(user, send_notif=True):
			count += 1

	db.session.commit()

	print(f"Updated {count} users", file=sys.stderr)


@celery.task()
def delete_old_notifications():
	one_month_ago = datetime.datetime.now() - datetime.timedelta(weeks=4)
	Notification.query.filter(Notification.read_at < one_month_ago).delete()
	db.session.commit()


@celery.task()
def delete_expired_sessions():
	UserSession.query.filter(UserSession.expired_filter()).delete(synchronize_session=False)
	db.session.commit()
