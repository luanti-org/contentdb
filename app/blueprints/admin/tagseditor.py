# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import redirect, render_template, abort, url_for, request
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import InputRequired, Length, Optional, Regexp

from . import bp
from app.models import Permission, Tag, db, AuditSeverity
from app.utils import add_audit_log, normalize_line_endings


@bp.route("/tags/")
@login_required
def tag_list():
	if not Permission.EDIT_TAGS.check(current_user):
		abort(403)

	query = Tag.query

	if request.args.get("sort") == "views":
		query = query.order_by(db.desc(Tag.views))
	else:
		query = query.order_by(db.asc(Tag.title))

	return render_template("admin/tags/list.html", tags=query.all())


class TagForm(FlaskForm):
	title = StringField("Title", [InputRequired(), Length(3, 100)])
	description = TextAreaField("Description", [Optional(), Length(0, 500)], filters=[normalize_line_endings])
	name = StringField("Name", [Optional(), Length(1, 20), Regexp("^[a-z0-9_]", 0,
			"Lower case letters (a-z), digits (0-9), and underscores (_) only")])
	submit = SubmitField("Save")


@bp.route("/tags/new/", methods=["GET", "POST"])
@bp.route("/tags/<name>/edit/", methods=["GET", "POST"])
@login_required
def create_edit_tag(name=None):
	tag = None
	if name is not None:
		tag = Tag.query.filter_by(name=name).first()
		if tag is None:
			abort(404)

	if not Permission.check_perm(current_user, Permission.EDIT_TAGS if tag else Permission.CREATE_TAG):
		abort(403)

	form = TagForm(obj=tag)
	if form.validate_on_submit():
		if tag is None:
			tag = Tag(form.title.data)
			tag.description = form.description.data
			db.session.add(tag)

			add_audit_log(AuditSeverity.EDITOR, current_user, f"Created tag {tag.name}",
						  url_for("admin.create_edit_tag", name=tag.name))
		else:
			form.populate_obj(tag)

			add_audit_log(AuditSeverity.EDITOR, current_user, f"Edited tag {tag.name}",
						  url_for("admin.create_edit_tag", name=tag.name))

		db.session.commit()

		if Permission.EDIT_TAGS.check(current_user):
			return redirect(url_for("admin.create_edit_tag", name=tag.name))
		else:
			return redirect(url_for("homepage.home"))

	return render_template("admin/tags/edit.html", tag=tag, form=form)
