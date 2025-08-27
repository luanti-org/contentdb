# ContentDB
# Copyright (C) 2022 rubenwardy
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

from flask import Blueprint, request, render_template, url_for, abort
from flask_babel import lazy_gettext
from flask_login import current_user
from flask_wtf import FlaskForm
from werkzeug.utils import redirect
from wtforms import TextAreaField, SubmitField, URLField, StringField, SelectField
from wtforms.validators import InputRequired, Length, Optional, DataRequired

from app.models import User, UserRank, Report, db, AuditSeverity, ReportCategory, Thread, Permission
from app.tasks.webhooktasks import post_discord_webhook
from app.utils import (is_no, abs_url_samesite, normalize_line_endings, rank_required, add_audit_log, abs_url_for,
					   random_string, add_replies)

bp = Blueprint("report", __name__)


class ReportForm(FlaskForm):
	category = SelectField(lazy_gettext("Category"), [DataRequired()], choices=ReportCategory.choices(with_none=True), coerce=ReportCategory.coerce)

	url = URLField(lazy_gettext("URL"), [Optional()])
	title = StringField(lazy_gettext("Subject / Title"), [InputRequired(), Length(10, 300)])
	message = TextAreaField(lazy_gettext("Message"), [Optional(), Length(0, 10000)], filters=[normalize_line_endings])
	submit = SubmitField(lazy_gettext("Report"))


@bp.route("/report/", methods=["GET", "POST"])
def report():
	is_anon = not current_user.is_authenticated or not is_no(request.args.get("anon"))

	url = request.args.get("url")
	if url:
		if url.startswith("/report/"):
			abort(404)

		url = abs_url_samesite(url)

	form = ReportForm(formdata=request.form) if current_user.is_authenticated else None
	if form and request.method == "GET":
		try:
			form.category.data = ReportCategory.coerce(request.args.get("category"))
		except KeyError:
			pass
		form.url.data = url
		form.title.data = request.args.get("title", "")

	if form and form.validate_on_submit():
		report = Report()
		report.id = random_string(8)
		report.user = current_user if current_user.is_authenticated else None
		form.populate_obj(report)

		if current_user.is_authenticated:
			thread = Thread()
			thread.title = f"Report: {form.title.data}"
			thread.author = current_user
			thread.private = True
			thread.watchers.extend(User.query.filter(User.rank >= UserRank.MODERATOR).all())
			db.session.add(thread)
			db.session.flush()

			report.thread = thread

			add_replies(thread, current_user, f"**{report.category.title} report created**\n\n{form.message.data}")
		else:
			ip_addr = request.headers.get("X-Forwarded-For") or request.remote_addr
			report.message = ip_addr + "\n\n" + report.message

		db.session.add(report)
		db.session.flush()

		if current_user.is_authenticated:
			add_audit_log(AuditSeverity.USER, current_user, f"New report: {report.title}",
					url_for("report.view", rid=report.id))

		db.session.commit()

		abs_url = abs_url_for("report.view", rid=report.id)
		msg = f"**New Report**\nReport on `{report.url}`\n\n{report.title}\n\nView: {abs_url}"
		post_discord_webhook.delay(None if is_anon else current_user.username, msg, True)

		return redirect(url_for("report.report_received", rid=report.id))

	return render_template("report/report.html", form=form, url=url, is_anon=is_anon, noindex=url is not None)


@bp.route("/report/received/")
def report_received():
	rid = request.args.get("rid")
	report = Report.query.get_or_404(rid)
	return render_template("report/report_received.html", report=report)


@bp.route("/admin/reports/")
@rank_required(UserRank.MODERATOR)
def list_all():
	reports = Report.query.order_by(db.asc(Report.is_resolved), db.asc(Report.created_at)).all()
	return render_template("report/list.html", reports=reports)


@bp.route("/admin/reports/<rid>/", methods=["GET", "POST"])
def view(rid: str):
	report = Report.query.get_or_404(rid)
	if not report.check_perm(current_user, Permission.SEE_REPORT):
		abort(404)

	if request.method == "POST":
		if report.is_resolved:
			if "reopen" in request.form:
				report.is_resolved = False
				url = url_for("report.view", rid=report.id)
				add_audit_log(AuditSeverity.MODERATION, current_user, f"Reopened report \"{report.title}\"", url)

				if report.thread:
					add_replies(report.thread, current_user, f"Reopened report", is_status_update=True)

				db.session.commit()
		else:
			if "completed" in request.form:
				outcome = "completed"
			elif "removed" in request.form:
				outcome = "content removed"
			elif "invalid" in request.form:
				outcome = "invalid"
			else:
				abort(400)

			report.is_resolved = True
			url = url_for("report.view", rid=report.id)
			add_audit_log(AuditSeverity.MODERATION, current_user, f"Resolved report as {outcome} \"{report.title}\"", url)

			if report.thread:
				add_replies(report.thread, current_user, f"Report closed as {outcome}", is_status_update=True)

			db.session.commit()

	return render_template("report/view.html", report=report)
