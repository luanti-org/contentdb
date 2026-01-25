# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import redirect, render_template, abort, url_for, request, flash
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField
from wtforms.validators import InputRequired, Length

from app.utils.user import rank_required
from app.utils.models import add_audit_log
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
