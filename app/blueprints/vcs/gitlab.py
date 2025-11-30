# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

from flask import request, jsonify

from app import csrf
from app.blueprints.api.support import error, api_create_vcs_release
from app.models import APIToken

from . import bp
from .common import get_packages_for_vcs_and_token


def webhook_impl():
	json = request.json

	# Get all tokens for package
	secret = request.headers.get("X-Gitlab-Token")
	if secret is None:
		return error(403, "Token required")

	token: APIToken = APIToken.query.filter_by(access_token=secret).first()
	if token is None:
		return error(403, "Invalid authentication")

	packages = get_packages_for_vcs_and_token(token, json["project"]["web_url"])
	for package in packages:
		#
		# Check event
		#
		event = json["event_name"]
		if event == "push":
			ref = json["after"]
			title = datetime.datetime.utcnow().strftime("%Y-%m-%d") + " " + ref[:5]
			branch = json["ref"].replace("refs/heads/", "")
			if package.update_config and package.update_config.ref:
				if branch != package.update_config.ref:
					continue
			elif branch not in ["master", "main"]:
				continue

		elif event == "tag_push":
			ref = json["ref"]
			title = ref.replace("refs/tags/", "")

		else:
			return error(400, "Unsupported event: '{}'. Only 'push', 'create:tag', and 'ping' are supported."
					.format(event or "null"))

		#
		# Perform release
		#
		if package.releases.filter_by(commit_hash=ref).count() > 0:
			continue

		return api_create_vcs_release(token, package, title, title, None, ref, reason="Webhook")

	return jsonify({
		"success": False,
		"message": "No release made. Either the release already exists or the event was filtered based on the branch"
	})



@bp.route("/gitlab/webhook/", methods=["POST"])
@csrf.exempt
def gitlab_webhook():
	try:
		return webhook_impl()
	except KeyError as err:
		return error(400, "Missing field: {}".format(err.args[0]))
