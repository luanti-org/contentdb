# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 rubenwardy <rw@rubenwardy>

import datetime
import typing
import json

from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import and_
from wtforms import SubmitField, SelectField, BooleanField
from wtforms.validators import Optional

from app.models import db, UserRank, User, PackageState, AuditSeverity, AuditLogEntry
from app.utils import rank_required, add_audit_log
from . import bp


class AuditForm(FlaskForm):
	min_rank = SelectField("Min rank", [Optional()], choices=UserRank.choices(), coerce=UserRank.coerce,
			default=UserRank.NEW_MEMBER)
	max_rank = SelectField("Max rank", [Optional()], choices=UserRank.choices(), coerce=UserRank.coerce,
			default=UserRank.ADMIN)
	hide_with_packages = BooleanField("Hide with approved packages", default=False)
	hide_with_anything = BooleanField("Hide with any content", default=False)
	hide_active = BooleanField("Hide with activity in last year", default=False)
	hide_with_forums = BooleanField("Hide with forum account", default=False)
	submit = SubmitField("Search", name=None)


mild_words = {
	"online",
	"gay",
	"live",
	"win",
	"vip",
	"club",
	"king",
}

suspicious_words = {
	"bet",
	"88",
	"777",
	"luck",
	"sport",
	"lottery",
	"casino",
	"assignment",
	"essay",
	"class",
	"bitcoin",
	"escort",
	"porn",
	"services",
	"crypto",
	"currency",
	"blockchain",
	"health",
	"ethereum",
	"nft",
	"recipe",
	"brand",
	"unblocked",
	"vpn",
	"marketing",
	"chatgpt",
	"google",
	"crackeado",
	"cracked",
	"torrent",
	"lawyer",
	"accident",
	"auction",
	"claims",
}

good_words = {
	"neocities.org",
	"github.io",
	"code",
}


def matches(value: typing.Optional[str], words: set[str]) -> float:
	if value is None:
		return 0
	lower = value.lower()
	return 1 if any(map(lambda x: x in lower, words)) else 0


def calc_spammer_likelihood(user: User) -> float:
	"""
	>= 100 is considered a likely spammer.
	"""
	score = 0

	score += matches(user.username, suspicious_words) * 100
	score += matches(user.website_url, suspicious_words) * 120
	score += matches(user.donate_url, suspicious_words) * 120

	score += matches(user.username, mild_words) * 20
	score += matches(user.website_url, mild_words) * 20
	score += matches(user.donate_url, mild_words) * 20

	score += 50 if user.website_url or user.donate_url else 0

	score -= matches(user.username, good_words) * 120
	score -= matches(user.website_url, good_words) * 120
	score += -200 if user.forums_username else 0

	return score


@bp.route("/admin/users/")
@rank_required(UserRank.MODERATOR)
def user_editor():
	form = AuditForm(request.args)
	query = User.query.filter(and_(User.rank >= form.min_rank.data, User.rank <= form.max_rank.data))

	if form.hide_with_anything.data:
		query = query.filter(and_(
			~User.packages.any(),
			~User.replies.any(),
			~User.reports.any(),
			~User.collections.any(),
			~User.reviews.any(),
		))
	elif form.hide_with_packages.data:
		query = query.filter(~User.packages.any(state=PackageState.APPROVED))

	if form.hide_active.data:
		one_year_ago = datetime.datetime.now() - datetime.timedelta(days=365)
		query = query.filter(~User.audit_log_entries.any(AuditLogEntry.created_at > one_year_ago))

	if form.hide_with_forums.data:
		query = query.filter(User.forums_username.is_(None))

	users = query.all()

	scored_users = [[calc_spammer_likelihood(user), user] for user in users]
	scored_users = sorted(scored_users, key=lambda x: x[0], reverse=True)
	return render_template("admin/users.html", form=form, scored_users=scored_users)


@bp.route("/admin/users/delete/", methods=["POST"])
@rank_required(UserRank.MODERATOR)
def user_editor_delete():
	selected = request.form.getlist("selected")
	confirmed = request.form.get("confirm", None)
	if confirmed:
		for username in selected:
			user: User = User.query.filter_by(username=username).first()
			if user is None:
				continue

			msg = f"Deleted user {user.username} as spammer"
			desc = f"{json.dumps(user.get_dict(), indent=4)}"
			add_audit_log(AuditSeverity.MODERATION, current_user, msg, None, None, desc)

			for pkg in user.packages.all():
				pkg.review_thread = None
				db.session.delete(pkg)

			db.session.delete(user)
		db.session.commit()

		flash(f"Deleted {len(selected)} users", "success")
		return redirect(url_for("admin.user_editor"))

	selected_users = User.query.filter(User.username.in_(selected)).all()
	return render_template("admin/users_delete.html", selected=selected_users)
