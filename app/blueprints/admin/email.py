# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import request, abort, url_for, redirect, render_template, flash
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField, StringField
from wtforms.validators import InputRequired, Length

from app.markdown import render_markdown
from app.tasks.emails import send_user_email, send_bulk_email as task_send_bulk
from app.utils import rank_required, add_audit_log, normalize_line_endings
from . import bp
from app.models import UserRank, User, AuditSeverity


class SendEmailForm(FlaskForm):
	subject = StringField("Subject", [InputRequired(), Length(1, 300)])
	text    = TextAreaField("Message", [InputRequired()], filters=[normalize_line_endings])
	submit  = SubmitField("Send")


@bp.route("/admin/send-email/", methods=["GET", "POST"])
@rank_required(UserRank.ADMIN)
def send_single_email():
	username = request.args["username"]
	user = User.query.filter_by(username=username).first()
	if user is None:
		abort(404)

	next_url = url_for("users.profile", username=user.username)

	if user.email is None:
		flash("User has no email address!", "danger")
		return redirect(next_url)

	form = SendEmailForm(request.form)
	if form.validate_on_submit():
		add_audit_log(AuditSeverity.MODERATION, current_user,
				"Sent email to {}".format(user.display_name), url_for("users.profile", username=username))

		text = form.text.data
		html = render_markdown(text)
		task = send_user_email.delay(user.email, user.locale or "en", form.subject.data, text, html)
		return redirect(url_for("tasks.check", id=task.id, r=next_url))

	return render_template("admin/send_email.html", form=form, user=user)


@bp.route("/admin/send-bulk-email/", methods=["GET", "POST"])
@rank_required(UserRank.ADMIN)
def send_bulk_email():
	form = SendEmailForm(request.form)
	if form.validate_on_submit():
		add_audit_log(AuditSeverity.MODERATION, current_user,
				"Sent bulk email", url_for("admin.admin_page"), None, form.text.data)

		text = form.text.data
		html = render_markdown(text)
		task_send_bulk.delay(form.subject.data, text, html)

		return redirect(url_for("admin.admin_page"))

	return render_template("admin/send_bulk_email.html", form=form)
