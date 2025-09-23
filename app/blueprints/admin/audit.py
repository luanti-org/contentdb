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

from flask import render_template, request, abort
from flask_babel import lazy_gettext
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import Optional, Length

from app.models import db, AuditLogEntry, UserRank, User, Permission
from app.utils import rank_required, get_int_or_abort

from . import bp


class AuditForm(FlaskForm):
	username = StringField(lazy_gettext("Username"), [Optional(), Length(0, 25)])
	q = StringField(lazy_gettext("Query"), [Optional(), Length(0, 300)])
	url = StringField(lazy_gettext("URL"), [Optional(), Length(0, 300)])
	submit = SubmitField(lazy_gettext("Search"), name=None)


@bp.route("/admin/audit/")
@rank_required(UserRank.APPROVER)
def audit():
	page = get_int_or_abort(request.args.get("page"), 1)
	num = min(40, get_int_or_abort(request.args.get("n"), 100))

	query = AuditLogEntry.query.order_by(db.desc(AuditLogEntry.created_at))

	form = AuditForm(request.args)
	username = form.username.data
	q = form.q.data
	url = form.url.data
	if username:
		user = User.query.filter_by(username=username).first_or_404()
		query = query.filter_by(causer=user)

	if q:
		query = query.filter(AuditLogEntry.title.ilike(f"%{q}%"))

	if url:
		query = query.filter(AuditLogEntry.url.ilike(f"%{url}%"))

	if not current_user.rank.at_least(UserRank.MODERATOR):
		query = query.filter(AuditLogEntry.package)

	pagination = query.paginate(page=page, per_page=num)
	return render_template("admin/audit.html", log=pagination.items, pagination=pagination, form=form)


@bp.route("/admin/audit/<int:id_>/")
@login_required
def audit_view(id_):
	entry: AuditLogEntry = AuditLogEntry.query.get_or_404(id_)
	if not entry.check_perm(current_user, Permission.VIEW_AUDIT_DESCRIPTION):
		abort(403)

	return render_template("admin/audit_view.html", entry=entry)
