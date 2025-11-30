# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask_babel import gettext
from flask_login import current_user

from . import bp
from flask import redirect, render_template, session, request, flash, url_for
from app.models import db, User, UserRank
from app.utils import random_string, login_user_set_active
from app.tasks.forumtasks import check_forum_account
from app.utils.phpbbparser import get_profile


@bp.route("/user/claim/", methods=["GET", "POST"])
def claim():
	return render_template("users/claim.html")


@bp.route("/user/claim-forums/", methods=["GET", "POST"])
def claim_forums():
	if current_user.is_authenticated:
		return redirect(url_for("homepage.home"))

	username = request.args.get("username")
	if username is None:
		username = ""
	else:
		method = request.args.get("method")

		user = User.query.filter_by(forums_username=username).first()
		if user and user.rank.at_least(UserRank.NEW_MEMBER):
			flash(gettext("User has already been claimed"), "danger")
			return redirect(url_for("users.claim_forums"))
		elif method == "github":
			if user is None or user.github_username is None:
				flash(gettext("Unable to get GitHub username for user. Make sure the forum account exists."), "danger")
				return redirect(url_for("users.claim_forums", username=username))
			else:
				return redirect(url_for("vcs.github_start"))

	if "forum_token" in session:
		token = session["forum_token"]
	else:
		token = random_string(12)
		session["forum_token"] = token

	if request.method == "POST":
		ctype = request.form.get("claim_type")
		username = request.form.get("username")

		if User.query.filter(User.username == username, User.forums_username.is_(None)).first():
			flash(gettext("A ContentDB user with that name already exists. Please contact an admin to link to your forum account"), "danger")
			return redirect(url_for("users.claim_forums"))

		if ctype == "github":
			task = check_forum_account.delay(username)
			return redirect(url_for("tasks.check", id=task.id, r=url_for("users.claim_forums", username=username, method="github")))
		elif ctype == "forum":
			user = User.query.filter_by(forums_username=username).first()
			if user is not None and user.rank.at_least(UserRank.NEW_MEMBER):
				flash(gettext("That user has already been claimed!"), "danger")
				return redirect(url_for("users.claim_forums"))

			# Get signature
			try:
				profile = get_profile("https://forum.luanti.org", username)
				sig = profile.signature if profile else None
			except IOError as e:
				if hasattr(e, 'message'):
					message = e.message
				else:
					message = str(e)

				flash(gettext(u"Error whilst attempting to access forums: %(message)s", message=message), "danger")
				return redirect(url_for("users.claim_forums", username=username))

			if profile is None:
				flash(gettext("Unable to get forum signature - does the user exist?"), "danger")
				return redirect(url_for("users.claim_forums", username=username))

			# Look for key
			if sig and token in sig:
				# Try getting again to fix crash
				user = User.query.filter_by(forums_username=username).first()
				if user is None:
					user = User(username)
					user.forums_username = username
					db.session.add(user)
					db.session.commit()

				ret = login_user_set_active(user, remember=True)
				if ret is None:
					flash(gettext("Unable to login as user"), "danger")
					return redirect(url_for("users.claim_forums", username=username))

				return ret

			else:
				flash(gettext("Could not find the key in your signature!"), "danger")
				return redirect(url_for("users.claim_forums", username=username))
		else:
			flash(gettext("Unknown claim type"), "danger")

	return render_template("users/claim_forums.html", username=username, key="cdb_" + token)
