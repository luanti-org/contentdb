# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import re
from functools import wraps
from typing import Optional

from flask_babel import gettext
from flask_login import login_user, logout_user, current_user
from passlib.handlers.bcrypt import bcrypt
from flask import redirect, url_for, abort, flash, g
from sqlalchemy.orm import joinedload
from werkzeug.local import LocalProxy

from app.utils.flask import is_safe_url
from app.utils.misc import random_string, hash_token
from app.models import User, UserRank, UserNotificationPreferences, UserSession, db


def is_username_valid(username: str) -> bool:
	return username is not None and len(username) >= 2 and \
			bool(re.match(r"^[A-Za-z0-9._-]*$", username)) and not re.match(r"^\.*$", username)


def make_valid_username(username: str) -> str:
	return re.sub(r"[^A-Za-z0-9._-]+", "_", username)


def _unwrap_user(user: User) -> User:
	if isinstance(user, LocalProxy):
		return user._get_current_object()
	return user


def login_user_with_session(user: User, remember: bool = False, force: bool = False) -> bool:
	"""
	Starts a new login session and logs the user into it.
	Use this instead of flask_login.login_user.
	Commits the database session.
	"""
	user = _unwrap_user(user)
	if not force and not user.is_active:
		return False

	# End current sessions, as they're being replaced
	if current_user.is_authenticated and current_user._session_id is not None:
		UserSession.query.filter_by(id=current_user._session_id).delete(synchronize_session=False)

	token = random_string(64)
	user_session = UserSession()
	user_session.user = user
	user_session.token_hash = hash_token(token)
	db.session.add(user_session)
	db.session.commit()

	user._session_token = token
	user._session_id = user_session.id
	return login_user(user, remember=remember, force=force)


def load_user_from_session_token(token: str | None) -> User | None:
	"""
	Flask-Login user_loader. The token comes from the session or remember cookie.
	"""
	if not token:
		return None

	user_session = UserSession.query.options(joinedload(UserSession.user)) \
		.filter_by(token_hash=hash_token(token)).first()
	if user_session is None:
		return None

	# The loader can run part way through a request, so leave the writes to update_user_session()
	if user_session.is_expired:
		g.expired_user_session_id = user_session.id
		return None

	if user_session.last_used_at < datetime.datetime.utcnow() - UserSession.LAST_USED_RESOLUTION:
		g.stale_user_session_id = user_session.id

	user = user_session.user
	user._session_token = token
	user._session_id = user_session.id
	return user


def update_user_session():
	"""
	Deletes the current session if it expired, or updates its last_used_at.
	Must be the first before_request hook. At that point the request has only
	read from the database, so committing can't save changes that a view
	meant to discard.
	"""
	# Runs the user loader
	if not current_user.is_authenticated:
		expired_id = g.pop("expired_user_session_id", None)
		if expired_id is not None:
			UserSession.query.filter_by(id=expired_id).delete(synchronize_session=False)
			db.session.commit()
		return

	stale_id = g.pop("stale_user_session_id", None)
	if stale_id is not None:
		UserSession.query.filter_by(id=stale_id) \
			.update({"last_used_at": datetime.datetime.utcnow()}, synchronize_session=False)
		db.session.commit()


def logout_current_session():
	"""
	Ends the current login session, so that copies of the cookie stop working too.
	Use this instead of flask_login.logout_user.
	Commits the database session.
	"""
	if current_user.is_authenticated and current_user._session_id is not None:
		UserSession.query.filter_by(id=current_user._session_id).delete()
		db.session.commit()

	logout_user()


def end_user_sessions(user: User, keep_current: bool = False):
	"""
	Ends the user's login sessions on all devices.
	With keep_current, the session making this request continues if
	it belongs to the user. The caller must commit.
	"""
	query = UserSession.query.filter_by(user_id=user.id)
	if keep_current and current_user.is_authenticated and current_user.id == user.id and \
			current_user._session_id is not None:
		query = query.filter(UserSession.id != current_user._session_id)

	query.delete(synchronize_session=False)


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

	notif_count = user.notifications.filter_by(read_at=None).count()
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

	if login_user_with_session(user, *args, **kwargs):
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
