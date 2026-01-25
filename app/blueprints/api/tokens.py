# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import render_template, redirect, request, session, url_for, abort
from flask_babel import lazy_gettext
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import InputRequired, Length
from wtforms_sqlalchemy.fields import QuerySelectField

from app.models import db, User, APIToken, Permission
from app.utils.misc import random_string
from . import bp
from ..users.settings import get_setting_tabs


class CreateAPIToken(FlaskForm):
	name	     = StringField(lazy_gettext("Name"), [InputRequired(), Length(1, 30)])
	package      = QuerySelectField(lazy_gettext("Limit to package"), allow_blank=True,
			get_pk=lambda a: a.id, get_label=lambda a: a.title)
	submit	     = SubmitField(lazy_gettext("Save"))


@bp.route("/user/tokens/")
@login_required
def list_tokens_redirect():
	return redirect(url_for("api.list_tokens", username=current_user.username))


@bp.route("/users/<username>/tokens/")
@login_required
def list_tokens(username):
	user = User.query.filter_by(username=username).first()
	if user is None:
		abort(404)

	if not user.check_perm(current_user, Permission.CREATE_TOKEN):
		abort(403)

	return render_template("api/list_tokens.html", user=user, tabs=get_setting_tabs(user), current_tab="api_tokens")


@bp.route("/users/<username>/tokens/new/", methods=["GET", "POST"])
@bp.route("/users/<username>/tokens/<int:id>/edit/", methods=["GET", "POST"])
@login_required
def create_edit_token(username, id=None):
	user = User.query.filter_by(username=username).one_or_404()
	if not user.check_perm(current_user, Permission.CREATE_TOKEN):
		abort(403)

	is_new = id is None

	token = None
	access_token = None
	if not is_new:
		token = APIToken.query.get(id)
		if token is None or token.owner != user:
			abort(404)

		access_token = session.pop("token_" + str(token.id), None)

	form = CreateAPIToken(formdata=request.form, obj=token)
	form.package.query_factory = lambda: user.maintained_packages.all()

	if form.validate_on_submit():
		if is_new:
			token = APIToken()
			db.session.add(token)
			token.owner = user
			token.access_token = random_string(32)

		form.populate_obj(token)
		db.session.commit()

		if is_new:
			# Store token so it can be shown in the edit page
			session["token_" + str(token.id)] = token.access_token

		return redirect(url_for("api.create_edit_token", username=username, id=token.id))

	return render_template("api/create_edit_token.html", user=user, form=form, token=token, access_token=access_token)


@bp.route("/users/<username>/tokens/<int:id>/reset/", methods=["POST"])
@login_required
def reset_token(username, id):
	user = User.query.filter_by(username=username).first()
	if user is None:
		abort(404)

	if not user.check_perm(current_user, Permission.CREATE_TOKEN):
		abort(403)

	token = APIToken.query.get(id)
	if token is None:
		abort(404)
	elif token.owner != user:
		abort(403)

	token.access_token = random_string(32)

	db.session.commit() # save

	# Store token so it can be shown in the edit page
	session["token_" + str(token.id)] = token.access_token

	return redirect(url_for("api.create_edit_token", username=username, id=token.id))


@bp.route("/users/<username>/tokens/<int:id>/delete/", methods=["POST"])
@login_required
def delete_token(username, id):
	user = User.query.filter_by(username=username).first()
	if user is None:
		abort(404)

	if not user.check_perm(current_user, Permission.CREATE_TOKEN):
		abort(403)

	token = APIToken.query.get(id)
	if token is None:
		abort(404)
	elif token.owner != user:
		abort(403)

	db.session.delete(token)
	db.session.commit()

	return redirect(url_for("api.list_tokens", username=username))
