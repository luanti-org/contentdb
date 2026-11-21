# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import redirect, render_template, abort, url_for, request, flash
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileRequired
from wtforms import StringField, TextAreaField, SubmitField, RadioField, SelectMultipleField, FileField
from wtforms.widgets import CheckboxInput, ListWidget
from wtforms.validators import InputRequired, Length, Optional, Regexp, ValidationError

from . import bp
from app.domain.DomainError import DomainError
from app.domain.category_import import parse_category_csv, import_categories as do_import_categories
from app.models import Permission, Tag, db, AuditSeverity, TagKind, PackageType
from app.utils.models import add_audit_log
from app.utils.icons import is_icon
from app.utils.misc import normalize_line_endings


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


def coerce_package_type(item) -> PackageType:
	package_type = item if isinstance(item, PackageType) else PackageType.get(item)
	if package_type is None:
		# WTForms only turns ValueError into a validation error
		raise ValueError(f"Unknown package type {item}")
	return package_type


class TagForm(FlaskForm):
	title = StringField("Title", [InputRequired(), Length(3, 100)])
	description = TextAreaField("Description", [Optional(), Length(0, 500)], filters=[normalize_line_endings])
	name = StringField("Name", [Optional(), Length(1, 20), Regexp("^[a-z0-9_]", 0,
			"Lower case letters (a-z), digits (0-9), and underscores (_) only")])
	kind = RadioField("Kind", choices=TagKind.choices(), coerce=TagKind.coerce, default=TagKind.FEATURE.name)
	package_types = SelectMultipleField("Package types", choices=PackageType.choices(), coerce=coerce_package_type,
			widget=ListWidget(prefix_label=False), option_widget=CheckboxInput())
	icon = StringField("Icon", [Optional(), Length(1, 50)], filters=[lambda x: x.strip() if x else None])
	submit = SubmitField("Save")

	def validate_icon(self, field):
		if field.data and not is_icon(field.data):
			raise ValidationError("Not a Font Awesome 5 solid icon. Use its class name, such as fa-dragon")


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
			tag.kind = form.kind.data
			tag.package_types = form.package_types.data
			tag.icon = form.icon.data
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


class CategoryImportForm(FlaskForm):
	file = FileField("CSV file", [FileRequired()])
	preview = SubmitField("Preview")
	submit = SubmitField("Import")


MAX_CATEGORY_CSV_BYTES = 1024 * 1024


@bp.route("/tags/import-categories/", methods=["GET", "POST"])
@login_required
def import_categories():
	if not Permission.EDIT_TAGS.check(current_user):
		abort(403)

	form = CategoryImportForm()
	result = None
	applied = False
	if form.validate_on_submit():
		content = form.file.data.read(MAX_CATEGORY_CSV_BYTES + 1)
		applied = bool(form.submit.data)
		try:
			if len(content) > MAX_CATEGORY_CSV_BYTES:
				raise DomainError(400, "The file is too large")

			rows = parse_category_csv(content)
			result = do_import_categories(current_user, rows, applied)
		except DomainError as e:
			flash(e.message, "danger")
			applied = False

		if result and applied:
			add_audit_log(AuditSeverity.EDITOR, current_user,
					f"Imported categories for {len(result.changes)} games from a CSV file", url_for("admin.import_categories"))
			db.session.commit()
			flash(f"Changed the categories of {len(result.changes)} games", "success")

	return render_template("admin/tags/import_categories.html", form=form, result=result, applied=applied,
			categories=Tag.query.filter_by(kind=TagKind.CATEGORY).order_by(db.asc(Tag.title)).all())
