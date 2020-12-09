from flask import *
from flask_login import current_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms import *
from wtforms.validators import *

from app.models import *
from app.utils import nonEmptyOrNone, addAuditLog, randomString, rank_required
from app.tasks.emails import send_verify_email
from . import bp


def get_setting_tabs(user):
	return [
		{
			"id": "edit_profile",
			"title": "Edit Profile",
			"url": url_for("users.profile_edit", username=user.username)
		},
		{
			"id": "account",
			"title": "Account and Security",
			"url": url_for("users.account", username=user.username)
		},
		{
			"id": "notifications",
			"title": "Email and Notifications",
			"url": url_for("users.email_notifications", username=user.username)
		},
		{
			"id": "api_tokens",
			"title": "API Tokens",
			"url": url_for("api.list_tokens", username=user.username)
		},
	]


# Define the User profile form
class UserProfileForm(FlaskForm):
	display_name = StringField("Display name", [Optional(), Length(2, 100)])
	forums_username = StringField("Forums Username", [Optional(), Length(2, 50)])
	github_username = StringField("GitHub Username", [Optional(), Length(2, 50)])
	website_url = StringField("Website URL", [Optional(), URL()], filters = [lambda x: x or None])
	donate_url = StringField("Donation URL", [Optional(), URL()], filters = [lambda x: x or None])
	rank = SelectField("Rank", [Optional()], choices=UserRank.choices(), coerce=UserRank.coerce, default=UserRank.NEW_MEMBER)
	submit = SubmitField("Save")


@bp.route("/users/<username>/settings/profile/", methods=["GET", "POST"])
@login_required
def profile_edit(username):
	user : User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if not user.can_see_edit_profile(current_user):
		flash("Permission denied", "danger")
		return redirect(url_for("users.profile", username=username))


	form = UserProfileForm(formdata=request.form, obj=user)

	# Process valid POST
	if request.method=="POST" and form.validate():
		severity = AuditSeverity.NORMAL if current_user == user else AuditSeverity.MODERATION
		addAuditLog(severity, current_user, "Edited {}'s profile".format(user.display_name),
				url_for("users.profile", username=username))

		# Copy form fields to user_profile fields
		if user.checkPerm(current_user, Permission.CHANGE_USERNAMES):
			user.display_name = form.display_name.data
			user.forums_username = nonEmptyOrNone(form.forums_username.data)
			user.github_username = nonEmptyOrNone(form.github_username.data)

		if user.checkPerm(current_user, Permission.CHANGE_PROFILE_URLS):
			user.website_url  = form["website_url"].data
			user.donate_url   = form["donate_url"].data

		if user.checkPerm(current_user, Permission.CHANGE_RANK):
			newRank = form["rank"].data
			if current_user.rank.atLeast(newRank):
				if newRank != user.rank:
					user.rank = form["rank"].data
					msg = "Set rank of {} to {}".format(user.display_name, user.rank.getTitle())
					addAuditLog(AuditSeverity.MODERATION, current_user, msg, url_for("users.profile", username=username))
			else:
				flash("Can't promote a user to a rank higher than yourself!", "danger")

		# Save user_profile
		db.session.commit()

		return redirect(url_for("users.profile", username=username))

	# Process GET or invalid POST
	return render_template("users/profile_edit.html", user=user, form=form, tabs=get_setting_tabs(user), current_tab="edit_profile")




def make_settings_form():
	attrs = {
		"email": StringField("Email", [Optional(), Email()]),
		"submit": SubmitField("Save")
	}

	for notificationType in NotificationType:
		key = "pref_" + notificationType.toName()
		attrs[key] = BooleanField("")
		attrs[key + "_digest"] = BooleanField("")

	return type("SettingsForm", (FlaskForm,), attrs)

SettingsForm = make_settings_form()


def handle_email_notifications(user, prefs: UserNotificationPreferences, is_new, form):
	for notificationType in NotificationType:
		field_email = getattr(form, "pref_" + notificationType.toName()).data
		field_digest = getattr(form, "pref_" + notificationType.toName() + "_digest").data or field_email
		prefs.set_can_email(notificationType, field_email)
		prefs.set_can_digest(notificationType, field_digest)

	if is_new:
		db.session.add(prefs)

	if user.checkPerm(current_user, Permission.CHANGE_EMAIL):
		newEmail = form.email.data
		if newEmail and newEmail != user.email and newEmail.strip() != "":
			if EmailSubscription.query.filter_by(email=form.email.data, blacklisted=True).count() > 0:
				flash("That email address has been unsubscribed/blacklisted, and cannot be used", "danger")
				return

			token = randomString(32)

			severity = AuditSeverity.NORMAL if current_user == user else AuditSeverity.MODERATION

			msg = "Changed email of {}".format(user.display_name)
			addAuditLog(severity, current_user, msg, url_for("users.profile", username=user.username))

			ver = UserEmailVerification()
			ver.user = user
			ver.token = token
			ver.email = newEmail
			db.session.add(ver)
			db.session.commit()

			flash("Check your email to confirm it", "success")

			send_verify_email.delay(newEmail, token)
			return redirect(url_for("homepage.home"))

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

	if not user.checkPerm(current_user, Permission.CHANGE_EMAIL):
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
		data["pref_" + notificationType.toName()] = prefs.get_can_email(notificationType)
		data["pref_" + notificationType.toName() + "_digest"] = prefs.get_can_digest(notificationType)

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
		flash("Permission denied", "danger")
		return redirect(url_for("users.profile", username=username))

	return render_template("users/account.html", user=user, form=form, tabs=get_setting_tabs(user), current_tab="account")


@bp.route("/users/<username>/delete/", methods=["GET", "POST"])
@rank_required(UserRank.ADMIN)
def delete(username):
	user: User = User.query.filter_by(username=username).first()
	if not user:
		abort(404)

	if request.method == "GET":
		return render_template("users/delete.html", user=user, can_delete=user.can_delete())

	if user.can_delete():
		msg = "Deleted user {}".format(user.username)
		flash(msg, "success")
		addAuditLog(AuditSeverity.MODERATION, current_user, msg, None)

		db.session.delete(user)
	else:
		user.replies.delete()
		for thread in user.threads.all():
			db.session.delete(thread)
		user.email = None
		user.rank = UserRank.NOT_JOINED

		msg = "Deactivated user {}".format(user.username)
		flash(msg, "success")
		addAuditLog(AuditSeverity.MODERATION, current_user, msg, None)

	db.session.commit()

	if user == current_user:
		logout_user()

	return redirect(url_for("homepage.home"))
