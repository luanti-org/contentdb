# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


import datetime, requests
import os
import sys

from flask import url_for
from sqlalchemy import or_, and_, not_, func

from app import app
from app.models import User, db, UserRank, ThreadReply, Package, NotificationType
from app.utils import random_string
from app.utils.models import create_session, add_notification, get_system_user
from app.tasks import celery, TaskError


@celery.task()
def delete_inactive_users():
	threshold = datetime.datetime.now() - datetime.timedelta(hours=5)

	users = User.query.filter(User.is_active == False, User.packages == None, User.forum_topics == None,
			User.created_at <= threshold, User.rank == UserRank.NOT_JOINED).all()
	for user in users:
		db.session.delete(user)

	db.session.commit()


@celery.task()
def upgrade_new_members():
	with create_session() as session:
		threshold = datetime.datetime.now() - datetime.timedelta(days=7)

		session.query(User).filter(and_(User.rank == UserRank.NEW_MEMBER, or_(
				User.replies.any(ThreadReply.created_at < threshold),
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

	filename = random_string(10) + "." + ext
	filepath = os.path.join(app.config["UPLOAD_DIR"], filename)
	with open(filepath, "wb") as f:
		size = 0
		for chunk in resp.iter_content(chunk_size=1024):
			if chunk:  # filter out keep-alive new chunks
				size += len(chunk)
				if size > 3 * 1000 * 1000:  # 3 MB
					raise TaskError(f"File too large to download {url}")

				f.write(chunk)

	user.profile_pic = "/uploads/" + filename
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
def do_delete_likely_spammers():
	query = (User.query.filter(
		and_(
			User.rank == UserRank.NEW_MEMBER,
			or_(
				func.replace(User.website_url, ".", "").regexp_match(
					func.concat("https?://[^/]*", User.username, ".*")),
			),
			or_(
				User.website_url.ilike("%bet%"),
				User.website_url.ilike("%win%"),
				User.website_url.ilike("%88%"),
				User.website_url.ilike("%luck%"),
				User.website_url.ilike("%sport%"),
				User.website_url.ilike("%lottery%"),
				User.website_url.ilike("%casino%"),
				User.website_url.ilike("%vip%"),
				User.website_url.ilike("%assignment%"),
			),
			~User.packages.any(),
			~User.replies.any(),
			~User.reports.any(),
			not_(or_(
				User.website_url.ilike("%.github.io%"),
				User.website_url.ilike("%.neocities.org%"),
			)),
		)))

	for user in query.all():
		db.session.delete(user)
	db.session.commit()
