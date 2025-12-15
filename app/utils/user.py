# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from functools import wraps
from typing import Optional

from flask_babel import gettext
from flask_login import login_user, current_user
from passlib.handlers.bcrypt import bcrypt
from flask import redirect, url_for, abort, flash

from app.utils import is_safe_url
from app.models import User, UserRank, UserNotificationPreferences, db


def check_password_hash(stored, given):
	if stored is None or stored == "":
		return False

	return bcrypt.verify(given.encode("UTF-8"), stored)


def make_flask_login_password(plaintext):
	return bcrypt.hash(plaintext.encode("UTF-8"))


def post_login(user: User, next_url):
	if next_url and is_safe_url(next_url):
		return redirect(next_url)

	if not current_user.password:
		return redirect(url_for("users.set_password"))

	notif_count = user.notifications.count()
	if notif_count > 0:
		if notif_count >= 10:
			flash(gettext("You have a lot of notifications, you should either read or clear them"), "info")
		return redirect(url_for("notifications.list_all"))

	if user.notification_preferences is None:
		flash(gettext("Please consider enabling email notifications, you can customise how much is sent"), "info")
		return redirect(url_for("users.email_notifications", username=user.username))

	return redirect(url_for("homepage.home"))


def login_user_set_active(user: User, next_url: Optional[str] = None, *args, **kwargs):
	if user.rank == UserRank.NOT_JOINED and user.email is None:
		user.rank = UserRank.NEW_MEMBER
		user.notification_preferences = UserNotificationPreferences(user)
		user.is_active = True
		db.session.commit()

	if login_user(user, *args, **kwargs):
		return post_login(user, next_url)

	return None


def rank_required(rank):
	def decorator(f):
		@wraps(f)
		def decorated_function(*args, **kwargs):
			if not current_user.is_authenticated:
				return redirect(url_for("users.login"))
			if not current_user.rank.at_least(rank):
				abort(403)

			return f(*args, **kwargs)

		return decorated_function
	return decorator
