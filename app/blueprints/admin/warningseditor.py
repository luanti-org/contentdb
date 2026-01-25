# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import redirect, render_template, abort, url_for, request
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Length, Optional, Regexp

from app.utils.user import rank_required
from app.utils.misc import normalize_line_endings
from . import bp
from app.models import UserRank, ContentWarning, db


@bp.route("/admin/warnings/")
@rank_required(UserRank.ADMIN)
def warning_list():
	return render_template("admin/warnings/list.html", warnings=ContentWarning.query.order_by(db.asc(ContentWarning.title)).all())


class WarningForm(FlaskForm):
	title = StringField("Title", [InputRequired(), Length(3, 100)])
	description = TextAreaField("Description", [Optional(), Length(0, 500)], filters=[normalize_line_endings])
	name = StringField("Name", [Optional(), Length(1, 20),
					Regexp("^[a-z0-9_]", 0, "Lower case letters (a-z), digits (0-9), and underscores (_) only")])
	submit = SubmitField("Save")


@bp.route("/admin/warnings/new/", methods=["GET", "POST"])
@bp.route("/admin/warnings/<name>/edit/", methods=["GET", "POST"])
@rank_required(UserRank.ADMIN)
def create_edit_warning(name=None):
	warning = None
	if name is not None:
		warning = ContentWarning.query.filter_by(name=name).first()
		if warning is None:
			abort(404)

	form = WarningForm(formdata=request.form, obj=warning)
	if form.validate_on_submit():
		if warning is None:
			warning = ContentWarning(form.title.data, form.description.data)
			db.session.add(warning)
		else:
			form.populate_obj(warning)
		db.session.commit()

		return redirect(url_for("admin.warning_list"))

	return render_template("admin/warnings/edit.html", warning=warning, form=form)
