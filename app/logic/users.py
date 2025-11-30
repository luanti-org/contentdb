# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Optional

from flask import flash, redirect, url_for
from flask_babel import gettext, get_locale
from sqlalchemy import or_
from werkzeug import Response

from app.models import User, UserRank, PackageAlias, EmailSubscription, UserNotificationPreferences, db
from app.utils import is_username_valid
from app.tasks.emails import send_anon_email


def create_user(username: str, display_name: str, email: Optional[str], oauth_provider: Optional[str] = None) -> None | Response | User:
	if not is_username_valid(username):
		flash(gettext("Username is invalid"))
		return

	user_by_name = User.query.filter(or_(
			User.username == username,
			User.username == display_name,
			User.display_name == display_name,
			User.forums_username == username,
			User.github_username == username)).first()
	if user_by_name:
		if user_by_name.rank == UserRank.NOT_JOINED and user_by_name.forums_username:
			flash(gettext("An account already exists for that username but hasn't been claimed yet."), "danger")
			return redirect(url_for("users.claim_forums", username=user_by_name.forums_username))
		elif oauth_provider:
			flash(gettext("Unable to create an account as the username is already taken. "
					"If you meant to log in, you need to connect %(provider)s to your account first", provider=oauth_provider), "danger")
			return
		else:
			flash(gettext("That username/display name is already in use, please choose another."), "danger")
			return

	alias_by_name = (PackageAlias.query
			.filter(or_(PackageAlias.author == username, PackageAlias.author == display_name))
			.first())
	if alias_by_name:
		flash(gettext("Unable to create an account as the username was used in the past."), "danger")
		return

	if email:
		user_by_email = User.query.filter_by(email=email).first()
		if user_by_email:
			send_anon_email.delay(email, get_locale().language, gettext("Email already in use"),
				gettext("We were unable to create the account as the email is already in use by %(display_name)s. Try a different email address.",
						display_name=user_by_email.display_name))
			return redirect(url_for("users.email_sent"))
		elif EmailSubscription.query.filter_by(email=email, blacklisted=True).count() > 0:
			flash(gettext("That email address has been unsubscribed/blacklisted, and cannot be used"), "danger")
			return

	user = User(username, False, email)
	user.notification_preferences = UserNotificationPreferences(user)
	if display_name:
		user.display_name = display_name
	db.session.add(user)

	return user
