# ContentDB
# Copyright (C) 2018-21 rubenwardy
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


from flask import redirect, render_template, abort, url_for, request, flash
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField
from wtforms.validators import InputRequired, Length

from app.utils import rank_required, add_audit_log
from . import bp
from app.models import UserRank, LuantiRelease, db, AuditSeverity


@bp.route("/versions/")
@rank_required(UserRank.MODERATOR)
def version_list():
	return render_template("admin/versions/list.html",
			versions=LuantiRelease.query.order_by(db.asc(LuantiRelease.id)).all())


class VersionForm(FlaskForm):
	name = StringField("Name", [InputRequired(), Length(3, 100)])
	protocol = IntegerField("Protocol")
	submit = SubmitField("Save")


@bp.route("/versions/new/", methods=["GET", "POST"])
@bp.route("/versions/<name>/edit/", methods=["GET", "POST"])
@rank_required(UserRank.MODERATOR)
def create_edit_version(name=None):
	version = None
	if name is not None:
		version = LuantiRelease.query.filter_by(name=name).first()
		if version is None:
			abort(404)

	form = VersionForm(formdata=request.form, obj=version)
	if form.validate_on_submit():
		if version is None:
			version = LuantiRelease(form.name.data)
			db.session.add(version)
			flash("Created version " + form.name.data, "success")

			add_audit_log(AuditSeverity.MODERATION, current_user, f"Created version {version.name}",
						  url_for("admin.license_list"))
		else:
			flash("Updated version " + form.name.data, "success")

			add_audit_log(AuditSeverity.MODERATION, current_user, f"Edited version {version.name}",
						  url_for("admin.version_list"))

		form.populate_obj(version)
		db.session.commit()
		return redirect(url_for("admin.version_list"))

	return render_template("admin/versions/edit.html", version=version, form=form)
