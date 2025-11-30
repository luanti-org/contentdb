# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import urllib.parse as urlparse
from urllib.parse import urlencode

import typing
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, abort, make_response, flash
from flask_babel import lazy_gettext, gettext
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, URLField, SelectField
from wtforms.validators import InputRequired, Length, Optional

from app import csrf
from app.blueprints.users.settings import get_setting_tabs
from app.models import db, OAuthClient, User, Permission, APIToken, AuditSeverity, UserRank
from app.utils import random_string, add_audit_log

bp = Blueprint("oauth", __name__)


def build_redirect_url(url: str, code: str, state: typing.Optional[str]):
	params = {"code": code}
	if state is not None:
		params["state"] = state
	url_parts = list(urlparse.urlparse(url))
	query = dict(urlparse.parse_qsl(url_parts[4]))
	query.update(params)
	url_parts[4] = urlencode(query)
	return urlparse.urlunparse(url_parts)


@bp.route("/oauth/authorize/", methods=["GET", "POST"])
@login_required
def oauth_start():
	response_type = request.args.get("response_type", "code")
	if response_type != "code":
		return "Unsupported response_type, only code is supported", 400

	client_id = request.args.get("client_id", "")
	if client_id == "":
		return "Missing client_id", 400

	redirect_uri = request.args.get("redirect_uri", "")
	if redirect_uri == "":
		return "Missing redirect_uri", 400

	client = OAuthClient.query.get_or_404(client_id)
	if client.redirect_url != redirect_uri:
		return "redirect_uri does not match client", 400

	if not client.approved and client.owner != current_user:
		abort(404)

	scope = request.args.get("scope", "public")
	if scope != "public":
		return "Unsupported scope, only public is supported", 400

	state = request.args.get("state")

	token = APIToken.query.filter(APIToken.client == client, APIToken.owner == current_user).first()
	if token:
		token.access_token = random_string(32)
		token.auth_code = random_string(32)
		db.session.commit()
		return redirect(build_redirect_url(client.redirect_url, token.auth_code, state))

	if request.method == "POST":
		action = request.form["action"]
		if action == "cancel":
			return redirect(client.redirect_url)

		elif action == "authorize":
			token = APIToken()
			token.access_token = random_string(32)
			token.name = f"Token for {client.title} by {client.owner.username}"
			token.owner = current_user
			token.client = client
			assert client is not None
			token.auth_code = random_string(32)
			db.session.add(token)

			add_audit_log(AuditSeverity.USER, current_user,
					f"Granted \"{scope}\" to OAuth2 application \"{client.title}\" by {client.owner.username} [{client_id}] ",
					url_for("users.profile", username=current_user.username))

			db.session.commit()

			return redirect(build_redirect_url(client.redirect_url, token.auth_code, state))

	return render_template("oauth/authorize.html", client=client)


def error(code: int, msg: str):
	abort(make_response(jsonify({"success": False, "error": msg}), code))


@bp.route("/oauth/token/", methods=["POST"])
@csrf.exempt
def oauth_grant():
	form = request.form

	grant_type = request.args.get("grant_type", "authorization_code")
	if grant_type != "authorization_code":
		error(400, "Unsupported grant_type, only authorization_code is supported")

	client_id = form.get("client_id", "")
	if client_id == "":
		error(400, "Missing client_id")

	client_secret = form.get("client_secret", "")
	if client_secret == "":
		error(400, "Missing client_secret")

	code = form.get("code", "")
	if code == "":
		error(400, "Missing code")

	client = OAuthClient.query.filter_by(id=client_id, secret=client_secret).first()
	if client is None:
		error(400, "client_id and/or client_secret is incorrect")

	token = APIToken.query.filter_by(auth_code=code).first()
	if token is None or token.client != client:
		error(400, "Incorrect code. It may have already been redeemed")

	token.auth_code = None
	db.session.commit()

	return jsonify({
		"success": True,
		"access_token": token.access_token,
		"token_type": "Bearer",
	})


@bp.route("/user/apps/")
@login_required
def list_clients_redirect():
	return redirect(url_for("oauth.list_clients", username=current_user.username))


@bp.route("/users/<username>/apps/")
@login_required
def list_clients(username):
	user = User.query.filter_by(username=username).first_or_404()
	if not user.check_perm(current_user, Permission.CREATE_OAUTH_CLIENT):
		abort(403)

	return render_template("oauth/list_clients.html", user=user, tabs=get_setting_tabs(user), current_tab="oauth_clients")


class OAuthClientForm(FlaskForm):
	title = StringField(lazy_gettext("Title"), [InputRequired(), Length(5, 30)])
	description = StringField(lazy_gettext("Description"), [Optional()])
	redirect_url = URLField(lazy_gettext("Redirect URL"), [InputRequired(), Length(5, 123)])
	app_type = SelectField(lazy_gettext("App Type"), [InputRequired()], choices=[
		("server", "Server-side (client_secret is kept safe)"),
		("client", "Client-side (client_secret is visible to all users)"),
	], coerce=lambda x: x)
	submit = SubmitField(lazy_gettext("Save"))


@bp.route("/users/<username>/apps/new/", methods=["GET", "POST"])
@bp.route("/users/<username>/apps/<id_>/edit/", methods=["GET", "POST"])
@login_required
def create_edit_client(username, id_=None):
	user = User.query.filter_by(username=username).first_or_404()
	if not user.check_perm(current_user, Permission.CREATE_OAUTH_CLIENT):
		abort(403)

	is_new = id_ is None
	client = None
	if id_ is not None:
		client = OAuthClient.query.get_or_404(id_)
		if client.owner != user:
			abort(404)

	form = OAuthClientForm(formdata=request.form, obj=client)

	if form.validate_on_submit():
		if is_new:
			if OAuthClient.query.filter(OAuthClient.title.ilike(form.title.data.strip())).count() > 0:
				flash(gettext("An OAuth client with that title already exists. Please choose a new title."), "danger")
				return render_template("oauth/create_edit.html", user=user, form=form, client=client)

			client = OAuthClient()
			db.session.add(client)
			client.owner = user
			client.id = random_string(24)
			client.secret = random_string(32)
			client.approved = current_user.rank.at_least(UserRank.EDITOR)


		form.populate_obj(client)

		verb = "Created" if is_new else "Edited"
		add_audit_log(AuditSeverity.NORMAL, current_user,
				f"{verb} OAuth2 application {client.title} by {client.owner.username} [{client.id}]",
				url_for("oauth.create_edit_client", username=client.owner.username, id_=client.id))

		db.session.commit()

		return redirect(url_for("oauth.create_edit_client", username=username, id_=client.id))

	return render_template("oauth/create_edit.html", user=user, form=form, client=client)


@bp.route("/users/<username>/apps/<id_>/delete/", methods=["POST"])
@login_required
def delete_client(username, id_):
	user = User.query.filter_by(username=username).first_or_404()
	if not user.check_perm(current_user, Permission.CREATE_OAUTH_CLIENT):
		abort(403)

	client = OAuthClient.query.get(id_)
	if client is None or client.owner != user:
		abort(404)

	add_audit_log(AuditSeverity.NORMAL, current_user,
			f"Deleted OAuth2 application {client.title} by {client.owner.username} [{client.id}]",
			url_for("users.profile", username=current_user.username))

	db.session.delete(client)
	db.session.commit()

	return redirect(url_for("oauth.list_clients", username=username))


@bp.route("/users/<username>/apps/<id_>/revoke-all/", methods=["POST"])
@login_required
def revoke_all(username, id_):
	user = User.query.filter_by(username=username).first_or_404()
	if not user.check_perm(current_user, Permission.CREATE_OAUTH_CLIENT):
		abort(403)

	client = OAuthClient.query.get(id_)
	if client is None or client.owner != user:
		abort(404)

	add_audit_log(AuditSeverity.NORMAL, current_user,
			f"Revoked all user tokens for OAuth2 application {client.title} by {client.owner.username} [{client.id}]",
			url_for("oauth.create_edit_client", username=client.owner.username, id_=client.id))

	client.tokens = []
	db.session.commit()

	flash(gettext("Revoked all user tokens"), "success")

	return redirect(url_for("oauth.create_edit_client", username=client.owner.username, id_=client.id))
