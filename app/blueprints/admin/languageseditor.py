# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import redirect, render_template, abort, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Length, Optional

from app.models import db, AuditSeverity, UserRank, Language, Package, PackageState, PackageTranslation
from app.utils import add_audit_log, rank_required, normalize_line_endings
from . import bp


@bp.route("/admin/languages/")
@rank_required(UserRank.ADMIN)
def language_list():
	at_least_one_count = db.session.query(PackageTranslation.package_id).group_by(PackageTranslation.package_id).count()
	total_package_count = Package.query.filter_by(state=PackageState.APPROVED).count()
	return render_template("admin/languages/list.html",
		languages=Language.query.all(), total_package_count=total_package_count,
		at_least_one_count=at_least_one_count)


class LanguageForm(FlaskForm):
	id = StringField("Id", [InputRequired(), Length(2, 10)])
	title = TextAreaField("Title", [Optional(), Length(2, 100)], filters=[normalize_line_endings])
	submit = SubmitField("Save")


@bp.route("/admin/languages/new/", methods=["GET", "POST"])
@bp.route("/admin/languages/<id_>/edit/", methods=["GET", "POST"])
@rank_required(UserRank.ADMIN)
def create_edit_language(id_=None):
	language = None
	if id_ is not None:
		language = Language.query.filter_by(id=id_).first()
		if language is None:
			abort(404)

	form = LanguageForm(obj=language)
	if form.validate_on_submit():
		if language is None:
			language = Language()
			db.session.add(language)
			form.populate_obj(language)

			add_audit_log(AuditSeverity.EDITOR, current_user, f"Created language {language.id}",
					url_for("admin.create_edit_language", id_=language.id))
		else:
			form.populate_obj(language)

			add_audit_log(AuditSeverity.EDITOR, current_user, f"Edited language {language.id}",
					url_for("admin.create_edit_language", id_=language.id))

		db.session.commit()
		return redirect(url_for("admin.create_edit_language", id_=language.id))

	return render_template("admin/languages/edit.html", language=language, form=form)
