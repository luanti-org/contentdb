# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>
import os

from flask import render_template, request, redirect, flash, url_for, abort
from flask_babel import lazy_gettext, gettext
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileRequired
from wtforms import StringField, SubmitField, BooleanField, FileField
from wtforms.validators import Length, DataRequired, Optional
from wtforms_sqlalchemy.fields import QuerySelectField

from app.logic.LogicError import LogicError
from app.logic.screenshots import do_create_screenshot, do_order_screenshots
from . import bp, get_package_tabs
from app.models import Permission, db, PackageScreenshot
from app.utils import is_package_page


class CreateScreenshotForm(FlaskForm):
	title	   = StringField(lazy_gettext("Title/Caption"), [Optional(), Length(-1, 100)])
	file_upload = FileField(lazy_gettext("File Upload"), [FileRequired()])
	submit	   = SubmitField(lazy_gettext("Save"))


class EditScreenshotForm(FlaskForm):
	title	 = StringField(lazy_gettext("Title/Caption"), [Optional(), Length(-1, 100)])
	approved = BooleanField(lazy_gettext("Is Approved"))
	submit   = SubmitField(lazy_gettext("Save"))


class EditPackageScreenshotsForm(FlaskForm):
	cover_image      = QuerySelectField(lazy_gettext("Cover Image"), [DataRequired()], allow_blank=True, get_pk=lambda a: a.id, get_label=lambda a: a.title)
	submit	         = SubmitField(lazy_gettext("Save"))


@bp.route("/packages/<author>/<name>/screenshots/", methods=["GET", "POST"])
@login_required
@is_package_page
def screenshots(package):
	if not package.check_perm(current_user, Permission.ADD_SCREENSHOTS):
		return redirect(package.get_url("packages.view"))

	form = EditPackageScreenshotsForm(obj=package)
	form.cover_image.query = package.screenshots

	if request.method == "POST":
		order = request.form.get("order")
		if order:
			try:
				do_order_screenshots(current_user, package, order.split(","))
				return redirect(package.get_url("packages.view"))
			except LogicError as e:
				flash(e.message, "danger")

		if form.validate_on_submit():
			form.populate_obj(package)
			db.session.commit()

	return render_template("packages/screenshots.html", package=package, form=form,
			tabs=get_package_tabs(current_user, package), current_tab="screenshots")


@bp.route("/packages/<author>/<name>/screenshots/new/", methods=["GET", "POST"])
@login_required
@is_package_page
def create_screenshot(package):
	if not package.check_perm(current_user, Permission.ADD_SCREENSHOTS):
		return redirect(package.get_url("packages.view"))

	# Initial form class from post data and default data
	form = CreateScreenshotForm()
	if form.validate_on_submit():
		try:
			do_create_screenshot(current_user, package, form.title.data, form.file_upload.data, False)
			return redirect(package.get_url("packages.screenshots"))
		except LogicError as e:
			flash(e.message, "danger")

	return render_template("packages/screenshot_new.html", package=package, form=form)


@bp.route("/packages/<author>/<name>/screenshots/<int:id>/edit/", methods=["GET", "POST"])
@login_required
@is_package_page
def edit_screenshot(package, id):
	screenshot = PackageScreenshot.query.get(id)
	if screenshot is None or screenshot.package != package:
		abort(404)

	can_edit = package.check_perm(current_user, Permission.ADD_SCREENSHOTS)
	can_approve = package.check_perm(current_user, Permission.APPROVE_SCREENSHOT)
	if not (can_edit or can_approve):
		return redirect(package.get_url("packages.screenshots"))

	# Initial form class from post data and default data
	form = EditScreenshotForm(obj=screenshot)
	if form.validate_on_submit():
		was_approved = screenshot.approved

		if can_edit:
			screenshot.title = form.title.data or "Untitled"

		if can_approve:
			screenshot.approved = form.approved.data
		else:
			screenshot.approved = was_approved

		db.session.commit()
		return redirect(package.get_url("packages.screenshots"))

	return render_template("packages/screenshot_edit.html", package=package, screenshot=screenshot, form=form)


@bp.route("/packages/<author>/<name>/screenshots/<int:id>/delete/", methods=["POST"])
@login_required
@is_package_page
def delete_screenshot(package, id):
	screenshot = PackageScreenshot.query.get(id)
	if screenshot is None or screenshot.package != package:
		abort(404)

	if not package.check_perm(current_user, Permission.ADD_SCREENSHOTS):
		flash(gettext("Permission denied"), "danger")
		return redirect(url_for("homepage.home"))

	if package.cover_image == screenshot:
		package.cover_image = None
		db.session.merge(package)

	db.session.delete(screenshot)
	db.session.commit()

	os.remove(screenshot.file_path)

	return redirect(package.get_url("packages.screenshots"))
