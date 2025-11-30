# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from celery import uuid
from flask import Blueprint, render_template, redirect, request, abort, url_for
from flask_babel import lazy_gettext
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, SelectMultipleField
from wtforms.validators import InputRequired, Length, Optional

from app.tasks import celery
from app.utils import rank_required

bp = Blueprint("zipgrep", __name__)

from app.models import UserRank, Package, PackageType
from app.tasks.zipgrep import search_in_releases


class SearchForm(FlaskForm):
	query = StringField(lazy_gettext("Text to find (regex)"), [InputRequired(), Length(1, 100)])
	file_filter = StringField(lazy_gettext("File filter"), [InputRequired(), Length(1, 100)], default="*.lua")
	type = SelectMultipleField(lazy_gettext("Type"), [Optional()],
			choices=PackageType.choices(), coerce=PackageType.coerce)
	submit = SubmitField(lazy_gettext("Search"))


@bp.route("/zipgrep/", methods=["GET", "POST"])
@rank_required(UserRank.EDITOR)
def zipgrep_search():
	form = SearchForm(request.form)
	if form.validate_on_submit():
		task_id = uuid()
		search_in_releases.apply_async((form.query.data, form.file_filter.data, [x.name for x in form.type.data]), task_id=task_id)
		result_url = url_for("zipgrep.view_results", id=task_id)
		return redirect(url_for("tasks.check", id=task_id, r=result_url))

	return render_template("zipgrep/search.html", form=form)


@bp.route("/zipgrep/<id>/")
def view_results(id):
	result = celery.AsyncResult(id)
	if result.status == "PENDING":
		abort(404)

	if result.status != "SUCCESS" or isinstance(result.result, Exception):
		result_url = url_for("zipgrep.view_results", id=id)
		return redirect(url_for("tasks.check", id=id, r=result_url))

	matches = result.result["matches"]
	for match in matches:
		match["package"] = Package.query.filter(
				Package.name == match["package"]["name"],
				Package.author.has(username=match["package"]["author"])).one()

	return render_template("zipgrep/view_results.html", query=result.result["query"], matches=matches)
