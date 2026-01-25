# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import redirect, abort, render_template, request, flash, url_for
from flask_babel import gettext, get_locale, lazy_gettext
from flask_login import current_user, login_required, logout_user
from flask_wtf import FlaskForm
from kombu import uuid
from sqlalchemy import or_
from wtforms import StringField, SubmitField, BooleanField, SelectField
from wtforms.validators import Length, Optional, Email, URL

from app.models import User, AuditSeverity, db, UserRank, PackageAlias, EmailSubscription, UserNotificationPreferences, \
	UserEmailVerification, Permission, NotificationType, UserBan
from app.tasks.emails import send_verify_email
from app.tasks.usertasks import update_github_user_id
from app.utils.misc import nonempty_or_none, random_string
from app.utils.models import add_audit_log
from app.utils.user import rank_required
from app.utils.flask import has_blocked_domains
from . import bp


def get_setting_tabs(user):
	ret = [
		{
			"id": "edit_profile",
			"title": gettext("Edit Profile"),
			"url": url_for("users.profile_edit", username=user.username)
		},
		{
			"id": "account",
			"title": gettext("Account and Security"),
			"url": url_for("users.account", username=user.username)
		},
		{
			"id": "notifications",
			"title": gettext("Email and Notifications"),
			"url": url_for("users.email_notifications", username=user.username)
		},
		{
			"id": "api_tokens",
			"title": gettext("API Tokens"),
			"url": url_for("api.list_tokens", username=user.username)
		},
	]

	if user.check_perm(current_user, Permission.CREATE_OAUTH_CLIENT):
		ret.append({
			"id": "oauth_clients",
			"title": gettext("OAuth2 Applications"),
			"url": url_for("oauth.list_clients", username=user.username)
		})

	if current_user.rank.at_least(UserRank.MODERATOR):
		ret.append({
			"id": "modtools",
			"title": gettext("Moderator Tools"),
			"url": url_for("users.modtools", username=user.username)
		})

	return ret


class UserProfileForm(FlaskForm):
	display_name = StringField(lazy_gettext("Display Name"), [Optional(), Length(1, 20)], filters=[lambda x: nonempty_or_none(x.strip())])
	website_url = StringField(lazy_gettext("Website URL"), [Optional(), URL()], filters = [lambda x: x or None])
	donate_url = StringField(lazy_gettext("Donation URL"), [Optional(), URL()], filters = [lambda x: x or None])
	submit = SubmitField(lazy_gettext("Save"))


def handle_profile_edit(form: UserProfileForm, user: User, username: str):
	severity = AuditSeverity.NORMAL if current_user == user else AuditSeverity.MODERATION
	add_audit_log(severity, current_user, "Edited {}'s profile".format(user.display_name),
				  url_for("users.profile", username=username))

	display_name = form.display_name.data or user.username
	if user.check_perm(current_user, Permission.CHANGE_DISPLAY_NAME) and \
			user.display_name != display_name:

		if User.query.filter(User.id != user.id,
				or_(User.username == display_name,
						User.display_name.ilike(display_name))).count() > 0:
			flash(gettext("A user already has that name"), "danger")
			return None


		alias_by_name = PackageAlias.query.filter(or_(
				PackageAlias.author == display_name)).first()
		if alias_by_name:
			flash(gettext("A user already has that name"), "danger")
			return

		user.display_name = display_name

		severity = AuditSeverity.USER if current_user == user else AuditSeverity.MODERATION
		add_audit_log(severity, current_user, "Changed display name of {} to {}"
					  .format(user.username, user.display_name),
					  url_for("users.profile", username=username))

	if user.check_perm(current_user, Permission.CHANGE_PROFILE_URLS):
		if has_blocked_domains(form.website_url.data, current_user.username, f"{user.username}'s website_url") or \
				has_blocked_domains(form.donate_url.data, current_user.username, f"{user.username}'s donate_url"):
			flash(gettext("Linking to blocked sites is not allowed"), "danger")
			return

		user.website_url = form.website_url.data
		user.donate_url = form.donate_url.data

	db.session.commit()

	return redirect(url_for("users.profile", username=username))


@bp.route("/users/<username>/settings/profile/", methods=["GET", "POST"])
@login_required
def profile_edit(username):
	user : User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.can_see_edit_profile(current_user):
		abort(403)

	form = UserProfileForm(obj=user)
	if form.validate_on_submit():
		ret = handle_profile_edit(form, user, username)
		if ret:
			return ret

	# Process GET or invalid POST
	return render_template("users/profile_edit.html", user=user, form=form, tabs=get_setting_tabs(user), current_tab="edit_profile")


def make_settings_form():
	attrs = {
		"email": StringField(lazy_gettext("Email"), [Optional(), Email()]),
		"submit": SubmitField(lazy_gettext("Save"))
	}

	for notificationType in NotificationType:
		key = "pref_" + notificationType.to_name()
		attrs[key] = BooleanField("")
		attrs[key + "_digest"] = BooleanField("")

	return type("SettingsForm", (FlaskForm,), attrs)

SettingsForm = make_settings_form()


def handle_email_notifications(user, prefs: UserNotificationPreferences, is_new, form):
	for notificationType in NotificationType:
		field_email = getattr(form, "pref_" + notificationType.to_name()).data
		field_digest = getattr(form, "pref_" + notificationType.to_name() + "_digest").data or field_email
		prefs.set_can_email(notificationType, field_email)
		prefs.set_can_digest(notificationType, field_digest)

	if is_new:
		db.session.add(prefs)

	if user.check_perm(current_user, Permission.CHANGE_EMAIL):
		newEmail = form.email.data
		if newEmail and newEmail != user.email and newEmail.strip() != "":
			if EmailSubscription.query.filter_by(email=form.email.data, blacklisted=True).count() > 0:
				flash(gettext("That email address has been unsubscribed/blacklisted, and cannot be used"), "danger")
				return

			token = random_string(32)

			severity = AuditSeverity.NORMAL if current_user == user else AuditSeverity.MODERATION

			msg = "Changed email of {}".format(user.display_name)
			add_audit_log(severity, current_user, msg, url_for("users.profile", username=user.username))

			ver = UserEmailVerification()
			ver.user = user
			ver.token = token
			ver.email = newEmail
			db.session.add(ver)
			db.session.commit()

			send_verify_email.delay(newEmail, token, get_locale().language)
			return redirect(url_for("users.email_sent"))

	db.session.commit()
	return redirect(url_for("users.email_notifications", username=user.username))


@bp.route("/user/settings/email/")
@bp.route("/users/<username>/settings/email/", methods=["GET", "POST"])
@login_required
def email_notifications(username=None):
	if username is None:
		return redirect(url_for("users.email_notifications", username=current_user.username))

	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.check_perm(current_user, Permission.CHANGE_EMAIL):
		abort(403)

	is_new = False
	prefs = user.notification_preferences
	if prefs is None:
		is_new = True
		prefs = UserNotificationPreferences(user)

	data = {}
	types = []
	for notificationType in NotificationType:
		types.append(notificationType)
		data["pref_" + notificationType.to_name()] = prefs.get_can_email(notificationType)
		data["pref_" + notificationType.to_name() + "_digest"] = prefs.get_can_digest(notificationType)

	data["email"] = user.email

	form = SettingsForm(data=data)
	if form.validate_on_submit():
		ret = handle_email_notifications(user, prefs, is_new, form)
		if ret:
			return ret

	return render_template("users/settings_email.html",
			form=form, user=user, types=types, is_new=is_new,
			tabs=get_setting_tabs(user), current_tab="notifications")


@bp.route("/users/<username>/settings/account/")
@login_required
def account(username):
	user : User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.can_see_edit_profile(current_user):
		abort(403)

	return render_template("users/account.html", user=user, tabs=get_setting_tabs(user), current_tab="account")


@bp.route("/users/<username>/settings/account/disconnect-github/", methods=["POST"])
def disconnect_github(username: str):
	user: User = User.query.filter_by(username=username).one_or_404()

	if not user.can_see_edit_profile(current_user):
		abort(403)

	if user.password and user.email:
		user.github_user_id = None
		user.github_username = None
		db.session.commit()

		flash(gettext("Removed GitHub account"), "success")
	else:
		flash(gettext("You need to add an email address and password before you can remove your GitHub account"), "danger")

	return redirect(url_for("users.account", username=username))


@bp.route("/users/<username>/delete/", methods=["GET", "POST"])
@rank_required(UserRank.ADMIN)
def delete(username):
	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if user.rank.at_least(UserRank.MODERATOR):
		flash(gettext("Users with moderator rank or above cannot be deleted"), "danger")
		return redirect(url_for("users.account", username=username))

	if request.method == "GET":
		return render_template("users/delete.html", user=user, can_delete=user.can_delete())

	if "delete" in request.form and (user.can_delete() or current_user.rank.at_least(UserRank.ADMIN)):
		msg = "Deleted user {}".format(user.username)
		flash(msg, "success")
		add_audit_log(AuditSeverity.MODERATION, current_user, msg, None)

		if current_user.rank.at_least(UserRank.ADMIN):
			for pkg in user.packages.all():
				pkg.review_thread = None
				db.session.delete(pkg)

		db.session.delete(user)
	elif "deactivate" in request.form:
		for reply in user.replies.all():
			db.session.delete(reply)
		for thread in user.threads.all():
			db.session.delete(thread)
		for token in user.tokens.all():
			db.session.delete(token)
		user.profile_pic = None
		user.email = None

		if user.rank != UserRank.BANNED:
			user.rank = UserRank.NOT_JOINED

		msg = "Deactivated user {}".format(user.username)
		flash(msg, "success")
		add_audit_log(AuditSeverity.MODERATION, current_user, msg, None)
	else:
		assert False

	db.session.commit()

	if user == current_user:
		logout_user()

	return redirect(url_for("homepage.home"))


class ModToolsForm(FlaskForm):
	username = StringField(lazy_gettext("Username"), [Optional(), Length(1, 50)])
	display_name = StringField(lazy_gettext("Display name"), [Optional(), Length(2, 100)])
	forums_username = StringField(lazy_gettext("Forums Username"), [Optional(), Length(2, 50)])
	github_username = StringField(lazy_gettext("GitHub Username"), [Optional(), Length(2, 50)])
	rank = SelectField(lazy_gettext("Rank"), [Optional()], choices=UserRank.choices(), coerce=UserRank.coerce,
			default=UserRank.NEW_MEMBER)
	submit = SubmitField(lazy_gettext("Save"))


@bp.route("/users/<username>/modtools/", methods=["GET", "POST"])
@rank_required(UserRank.MODERATOR)
def modtools(username):
	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.check_perm(current_user, Permission.CHANGE_EMAIL):
		abort(403)

	form = ModToolsForm(obj=user)
	if form.validate_on_submit():
		severity = AuditSeverity.NORMAL if current_user == user else AuditSeverity.MODERATION
		add_audit_log(severity, current_user, "Edited {}'s account".format(user.display_name),
					  url_for("users.profile", username=username))

		redirect_target = url_for("users.modtools", username=username)

		# Copy form fields to user_profile fields
		if user.check_perm(current_user, Permission.CHANGE_USERNAMES):
			if user.username != form.username.data:
				for package in user.packages:
					alias = PackageAlias(user.username, package.name)
					package.aliases.append(alias)
					db.session.add(alias)

				user.username = form.username.data

			user.display_name = form.display_name.data
			user.forums_username = nonempty_or_none(form.forums_username.data)
			github_username = nonempty_or_none(form.github_username.data)
			if github_username is None:
				user.github_username = None
				user.github_user_id = None
			else:
				task_id = uuid()
				update_github_user_id.apply_async((user.id, github_username), task_id=task_id)
				redirect_target = url_for("tasks.check", id=task_id, r=redirect_target)

		if user.check_perm(current_user, Permission.CHANGE_RANK):
			new_rank = form.rank.data
			if current_user.rank.at_least(new_rank):
				if new_rank != user.rank:
					user.rank = form.rank.data
					msg = "Set rank of {} to {}".format(user.display_name, user.rank.title)
					add_audit_log(AuditSeverity.MODERATION, current_user, msg,
								  url_for("users.profile", username=username))
			else:
				flash(gettext("Can't promote a user to a rank higher than yourself!"), "danger")

		db.session.commit()

		return redirect(redirect_target)

	return render_template("users/modtools.html", user=user, form=form, tabs=get_setting_tabs(user), current_tab="modtools")


@bp.route("/users/<username>/modtools/set-email/", methods=["POST"])
@rank_required(UserRank.MODERATOR)
def modtools_set_email(username):
	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.check_perm(current_user, Permission.CHANGE_EMAIL):
		abort(403)

	user.email = request.form["email"]
	user.is_active = False

	token = random_string(32)
	add_audit_log(AuditSeverity.MODERATION, current_user, f"Set email and sent a password reset on {user.username}",
				  url_for("users.profile", username=user.username), None)

	ver = UserEmailVerification()
	ver.user = user
	ver.token = token
	ver.email = user.email
	ver.is_password_reset = True
	db.session.add(ver)
	db.session.commit()

	send_verify_email.delay(user.email, token, user.locale or "en")

	flash(f"Set email and sent a password reset on {user.username}", "success")
	return redirect(url_for("users.modtools", username=username))


@bp.route("/users/<username>/modtools/ban/", methods=["POST"])
@rank_required(UserRank.MODERATOR)
def modtools_ban(username):
	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.check_perm(current_user, Permission.CHANGE_RANK):
		abort(403)

	message = request.form["message"]
	expires_at = request.form.get("expires_at")

	user.ban = UserBan()
	user.ban.banned_by = current_user
	user.ban.message = message

	if expires_at and expires_at != "":
		user.ban.expires_at = expires_at
	else:
		user.rank = UserRank.BANNED

	add_audit_log(AuditSeverity.MODERATION, current_user, f"Banned {user.username}, expires {user.ban.expires_at or '-'}, message: {message}",
				  url_for("users.profile", username=user.username), None)
	db.session.commit()

	flash(f"Banned {user.username}", "success")
	return redirect(url_for("users.modtools", username=username))


@bp.route("/users/<username>/modtools/unban/", methods=["POST"])
@rank_required(UserRank.MODERATOR)
def modtools_unban(username):
	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.check_perm(current_user, Permission.CHANGE_RANK):
		abort(403)

	if user.ban:
		db.session.delete(user.ban)

	if user.rank == UserRank.BANNED:
		user.rank = UserRank.MEMBER

	add_audit_log(AuditSeverity.MODERATION, current_user, f"Unbanned {user.username}",
				  url_for("users.profile", username=user.username), None)
	db.session.commit()

	flash(f"Unbanned {user.username}", "success")
	return redirect(url_for("users.modtools", username=username))
