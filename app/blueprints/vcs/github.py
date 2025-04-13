# ContentDB
# Copyright (C) 2018-24 rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import datetime
import hmac

import requests
from flask import abort, Response
from flask import redirect, url_for, request, flash, jsonify, current_app
from flask_babel import gettext
from flask_login import current_user

from app import github, csrf
from app.blueprints.api.support import error, api_create_vcs_release
from app.logic.users import create_user
from app.models import db, User, APIToken, AuditSeverity
from app.utils import abs_url_for, add_audit_log, login_user_set_active, is_safe_url
from . import bp
from .common import get_packages_for_vcs_and_token


@bp.route("/github/start/")
def github_start():
	next = request.args.get("next")
	if next and not is_safe_url(next):
		abort(400)

	return github.authorize("", redirect_uri=abs_url_for("vcs.github_callback", next=next))


@bp.route("/github/view/")
def github_view_permissions():
	url = "https://github.com/settings/connections/applications/" + \
			current_app.config["GITHUB_CLIENT_ID"]
	return redirect(url)


@bp.route("/github/callback/")
@github.authorized_handler
def github_callback(oauth_token):
	if oauth_token is None:
		flash(gettext("Authorization failed [err=gh-oauth-login-failed]"), "danger")
		return redirect(url_for("users.login"))

	next = request.args.get("next")
	if next and not is_safe_url(next):
		abort(400)

	redirect_to = next
	if redirect_to is None:
		redirect_to = url_for("homepage.home")

	# Get GitGub username
	url = "https://api.github.com/user"
	r = requests.get(url, headers={"Authorization": "token " + oauth_token})
	json = r.json()
	user_id = json["id"]
	github_username = json["login"]
	if type(user_id) is not int:
		abort(400)

	# Get user by GitHub user ID
	user_by_github = User.query.filter(User.github_user_id == user_id).one_or_none()

	# If logged in, connect
	if current_user and current_user.is_authenticated:
		if user_by_github is None:
			current_user.github_username = github_username
			current_user.github_user_id = user_id
			db.session.commit()
			flash(gettext("Linked GitHub to account"), "success")
			return redirect(redirect_to)
		elif user_by_github == current_user:
			return redirect(redirect_to)
		else:
			flash(gettext("GitHub account is already associated with another user: %(username)s",
					username=user_by_github.username), "danger")
			return redirect(redirect_to)

	# Log in to existing account
	elif user_by_github:
		ret = login_user_set_active(user_by_github, next, remember=True)
		if ret is None:
			flash(gettext("Authorization failed [err=gh-login-failed]"), "danger")
			return redirect(url_for("users.login"))

		user_by_github.github_username = github_username
		add_audit_log(AuditSeverity.USER, user_by_github, "Logged in using GitHub OAuth",
				url_for("users.profile", username=user_by_github.username))
		db.session.commit()
		return ret

	# Sign up
	else:
		user = create_user(github_username, github_username, None, "GitHub")
		if isinstance(user, Response):
			return user
		elif user is None:
			return redirect(url_for("users.login"))

		user.github_username = github_username
		user.github_user_id = user_id

		add_audit_log(AuditSeverity.USER, user, "Registered with GitHub, display name=" + user.display_name,
				url_for("users.profile", username=user.username))

		db.session.commit()

		ret = login_user_set_active(user, next, remember=True)
		if ret is None:
			flash(gettext("Authorization failed [err=gh-login-failed]"), "danger")
			return redirect(url_for("users.login"))

		return ret


def _find_api_token(header_signature: str) -> APIToken:
	sha_name, signature = header_signature.split('=')
	if sha_name != 'sha1':
		error(403, "Expected SHA1 payload signature")

	for token in APIToken.query.all():
		mac = hmac.new(token.access_token.encode("utf-8"), msg=request.data, digestmod='sha1')

		if hmac.compare_digest(str(mac.hexdigest()), signature):
			return token

	error(401, "Invalid authentication, couldn't validate API token")


@bp.route("/github/webhook/", methods=["POST"])
@csrf.exempt
def github_webhook():
	json = request.json

	header_signature = request.headers.get('X-Hub-Signature')
	if header_signature is None:
		return error(403, "Expected payload signature")

	token = _find_api_token(header_signature)
	packages = get_packages_for_vcs_and_token(token, "github.com/" + json["repository"]["full_name"])

	for package in packages:
		#
		# Check event
		#
		event = request.headers.get("X-GitHub-Event")
		if event == "push":
			ref = json["after"]
			title = datetime.datetime.utcnow().strftime("%Y-%m-%d") + " " + ref[:5]
			branch = json["ref"].replace("refs/heads/", "")
			if package.update_config and package.update_config.ref:
				if branch != package.update_config.ref:
					continue
			elif branch not in ["master", "main"]:
				continue

		elif event == "create":
			ref_type = json.get("ref_type")
			if ref_type != "tag":
				return jsonify({
					"success": False,
					"message": "Webhook ignored, as it's a non-tag create event. ref_type='{}'.".format(ref_type)
				})

			ref = json["ref"]
			title = ref

		elif event == "ping":
			return jsonify({"success": True, "message": "Ping successful"})

		else:
			return error(400, "Unsupported event: '{}'. Only 'push', 'create:tag', and 'ping' are supported."
					.format(event or "null"))

		#
		# Perform release
		#
		if package.releases.filter_by(commit_hash=ref).count() > 0:
			return

		return api_create_vcs_release(token, package, title, title, None, ref, reason="Webhook")

	return jsonify({
		"success": False,
		"message": "No release made. Either the release already exists or the event was filtered based on the branch"
	})
