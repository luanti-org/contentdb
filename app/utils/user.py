# ContentDB
# Copyright (C) 2018-21 rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


from functools import wraps

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
		return redirect(url_for("users.set_password", optional=True))

	notif_count = len(user.notifications)
	if notif_count > 0:
		if notif_count >= 10:
			flash(gettext("You have a lot of notifications, you should either read or clear them"), "info")
		return redirect(url_for("notifications.list_all"))

	if user.notification_preferences is None:
		flash(gettext("Please consider enabling email notifications, you can customise how much is sent"), "info")
		return redirect(url_for("users.email_notifications", username=user.username))

	return redirect(url_for("homepage.home"))


def login_user_set_active(user: User, next_url: str = None, *args, **kwargs):
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
			if not current_user.rank.atLeast(rank):
				abort(403)

			return f(*args, **kwargs)

		return decorated_function
	return decorator
