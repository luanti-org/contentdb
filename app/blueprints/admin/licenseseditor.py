# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import redirect, render_template, abort, url_for, request, flash
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, URLField
from wtforms.validators import InputRequired, Length, Optional

from app.utils.user import rank_required
from app.utils.misc import nonempty_or_none
from app.utils.models import add_audit_log
from . import bp
from app.models import UserRank, License, db, AuditSeverity


@bp.route("/licenses/")
@rank_required(UserRank.MODERATOR)
def license_list():
	return render_template("admin/licenses/list.html", licenses=License.query.order_by(db.asc(License.name)).all())


class LicenseForm(FlaskForm):
	name = StringField("Name", [InputRequired(), Length(3, 100)])
	is_foss = BooleanField("Is FOSS")
	url = URLField("URL", [Optional()], filters=[nonempty_or_none])
	submit = SubmitField("Save")


@bp.route("/licenses/new/", methods=["GET", "POST"])
@bp.route("/licenses/<name>/edit/", methods=["GET", "POST"])
@rank_required(UserRank.MODERATOR)
def create_edit_license(name=None):
	license = None
	if name is not None:
		license = License.query.filter_by(name=name).first()
		if license is None:
			abort(404)

	form = LicenseForm(formdata=request.form, obj=license)
	if request.method == "GET" and license is None:
		form.is_foss.data = True
	elif form.validate_on_submit():
		if license is None:
			license = License(form.name.data)
			db.session.add(license)
			flash("Created license " + form.name.data, "success")

			add_audit_log(AuditSeverity.MODERATION, current_user, f"Created license {license.name}",
						  url_for("admin.license_list"))
		else:
			flash("Updated license " + form.name.data, "success")

			add_audit_log(AuditSeverity.MODERATION, current_user, f"Edited license {license.name}",
						  url_for("admin.license_list"))

		form.populate_obj(license)
		db.session.commit()
		return redirect(url_for("admin.license_list"))

	return render_template("admin/licenses/edit.html", license=license, form=form)
