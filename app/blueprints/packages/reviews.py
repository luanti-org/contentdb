# ContentDB
# Copyright (C) 2020  rubenwardy
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

from collections import namedtuple

from flask import render_template, request, redirect, flash, url_for, abort
from flask_babel import gettext, lazy_gettext
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, RadioField
from wtforms.validators import InputRequired, Length

from app.models import db, PackageReview, Thread, ThreadReply, NotificationType, PackageReviewVote, Package, UserRank, \
	Permission, AuditSeverity, PackageState
from app.tasks.webhooktasks import post_discord_webhook
from app.utils import is_package_page, addNotification, get_int_or_abort, isYes, is_safe_url, rank_required, \
	addAuditLog, has_blocked_domains
from . import bp


@bp.route("/reviews/")
def list_reviews():
	page = get_int_or_abort(request.args.get("page"), 1)
	num = min(40, get_int_or_abort(request.args.get("n"), 100))

	pagination = PackageReview.query.order_by(db.desc(PackageReview.created_at)).paginate(page=page, per_page=num)
	return render_template("packages/reviews_list.html", pagination=pagination, reviews=pagination.items)


class ReviewForm(FlaskForm):
	title = StringField(lazy_gettext("Title"), [InputRequired(), Length(3,100)])
	comment = TextAreaField(lazy_gettext("Comment"), [InputRequired(), Length(10, 2000)])
	rating = RadioField(lazy_gettext("Rating"), [InputRequired()],
			choices=[("5", lazy_gettext("Yes")), ("3", lazy_gettext("Neutral")), ("1", lazy_gettext("No"))])
	submit  = SubmitField(lazy_gettext("Save"))


@bp.route("/packages/<author>/<name>/review/", methods=["GET", "POST"])
@login_required
@is_package_page
def review(package):
	if current_user in package.maintainers:
		flash(gettext("You can't review your own package!"), "danger")
		return redirect(package.get_url("packages.view"))

	if package.state != PackageState.APPROVED:
		abort(404)

	review = PackageReview.query.filter_by(package=package, author=current_user).first()
	can_review = review is not None or current_user.can_review_ratelimit()

	if not can_review:
		flash(gettext("You've reviewed too many packages recently. Please wait before trying again, and consider making your reviews more detailed"), "danger")

	form = ReviewForm(formdata=request.form, obj=review)

	# Set default values
	if request.method == "GET" and review:
		form.title.data = review.thread.title
		form.rating.data = str(review.rating)
		form.comment.data = review.thread.first_reply.comment

	# Validate and submit
	elif can_review and form.validate_on_submit():
		if has_blocked_domains(form.comment.data, current_user.username, f"review of {package.get_id()}"):
			flash(gettext("Linking to blocked sites is not allowed"), "danger")
		else:
			was_new = False
			if not review:
				was_new = True
				review = PackageReview()
				review.package = package
				review.author  = current_user
				db.session.add(review)

			review.rating = int(form.rating.data)

			thread = review.thread
			if not thread:
				thread = Thread()
				thread.author  = current_user
				thread.private = False
				thread.package = package
				thread.review = review
				db.session.add(thread)

				thread.watchers.append(current_user)

				reply = ThreadReply()
				reply.thread  = thread
				reply.author  = current_user
				reply.comment = form.comment.data
				db.session.add(reply)

				thread.replies.append(reply)
			else:
				reply = thread.first_reply
				reply.comment = form.comment.data

			thread.title   = form.title.data

			db.session.commit()

			package.recalculate_score()

			if was_new:
				notif_msg = "New review '{}'".format(form.title.data)
				type = NotificationType.NEW_REVIEW
			else:
				notif_msg = "Updated review '{}'".format(form.title.data)
				type = NotificationType.OTHER

			addNotification(package.maintainers, current_user, type, notif_msg,
					url_for("threads.view", id=thread.id), package)

			if was_new:
				post_discord_webhook.delay(thread.author.username,
						"Reviewed {}: {}".format(package.title, thread.get_view_url(absolute=True)), False)

			db.session.commit()

			return redirect(package.get_url("packages.view"))

	return render_template("packages/review_create_edit.html",
			form=form, package=package, review=review)


@bp.route("/packages/<author>/<name>/reviews/<reviewer>/delete/", methods=["POST"])
@login_required
@is_package_page
def delete_review(package, reviewer):
	review = PackageReview.query \
		.filter(PackageReview.package == package, PackageReview.author.has(username=reviewer)) \
		.first()
	if review is None or review.package != package:
		abort(404)

	if not review.check_perm(current_user, Permission.DELETE_REVIEW):
		abort(403)

	thread = review.thread

	reply = ThreadReply()
	reply.thread  = thread
	reply.author  = current_user
	reply.comment = "_converted review into a thread_"
	reply.is_status_update = True
	db.session.add(reply)

	thread.review = None

	msg = "Converted review by {} to thread".format(review.author.display_name)
	addAuditLog(AuditSeverity.MODERATION if current_user.username != reviewer else AuditSeverity.NORMAL,
			current_user, msg, thread.get_view_url(), thread.package)

	notif_msg = "Deleted review '{}', comments were kept as a thread".format(thread.title)
	addNotification(package.maintainers, current_user, NotificationType.OTHER, notif_msg, url_for("threads.view", id=thread.id), package)

	db.session.delete(review)

	package.recalculate_score()

	db.session.commit()

	return redirect(thread.get_view_url())


def handle_review_vote(package: Package, review_id: int):
	if current_user in package.maintainers:
		flash(gettext("You can't vote on the reviews on your own package!"), "danger")
		return

	review: PackageReview = PackageReview.query.get(review_id)
	if review is None or review.package != package:
		abort(404)

	if review.author == current_user:
		flash(gettext("You can't vote on your own reviews!"), "danger")
		return

	is_positive = isYes(request.form["is_positive"])

	vote = PackageReviewVote.query.filter_by(review=review, user=current_user).first()
	if vote is None:
		vote = PackageReviewVote()
		vote.review = review
		vote.user = current_user
		vote.is_positive = is_positive
		db.session.add(vote)
	elif vote.is_positive == is_positive:
		db.session.delete(vote)
	else:
		vote.is_positive = is_positive

	review.update_score()
	db.session.commit()


@bp.route("/packages/<author>/<name>/review/<int:review_id>/", methods=["POST"])
@login_required
@is_package_page
def review_vote(package, review_id):
	handle_review_vote(package, review_id)

	next_url = request.args.get("r")
	if next_url and is_safe_url(next_url):
		return redirect(next_url)
	else:
		return redirect(review.thread.get_view_url())


@bp.route("/packages/<author>/<name>/review-votes/")
@rank_required(UserRank.ADMIN)
@is_package_page
def review_votes(package):
	user_biases = {}
	for review in package.reviews:
		review_sign = review.as_weight()
		for vote in review.votes:
			user_biases[vote.user.username] = user_biases.get(vote.user.username, [0, 0])
			vote_sign = 1 if vote.is_positive else -1
			vote_bias = review_sign * vote_sign
			if vote_bias == 1:
				user_biases[vote.user.username][0] += 1
			else:
				user_biases[vote.user.username][1] += 1

	BiasInfo = namedtuple("BiasInfo", "username balance with_ against no_vote perc_with")
	user_biases_info = []
	for username, bias in user_biases.items():
		total_votes = bias[0] + bias[1]
		balance = bias[0] - bias[1]
		perc_with = round((100 * bias[0]) / total_votes)
		user_biases_info.append(BiasInfo(username, balance, bias[0], bias[1], len(package.reviews) - total_votes, perc_with))

	user_biases_info.sort(key=lambda x: -abs(x.balance))

	return render_template("packages/review_votes.html", package=package, reviews=package.reviews,
			user_biases=user_biases_info)
