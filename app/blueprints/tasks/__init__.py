# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import Blueprint, jsonify, url_for, request, redirect, render_template
from flask_login import login_required, current_user

from app import csrf
from app.models import UserRank
from app.tasks import celery
from app.tasks.importtasks import get_meta
from app.utils.flask import should_return_json

bp = Blueprint("tasks", __name__)


@csrf.exempt
@bp.route("/tasks/getmeta/new/", methods=["POST"])
@login_required
def start_getmeta():
	from flask import request
	author = request.args.get("author")
	author = current_user.forums_username if author is None else author
	aresult = get_meta.delay(request.args.get("url"), author)
	return jsonify({
		"poll_url": url_for("tasks.check", id=aresult.id),
	})


@bp.route("/tasks/<id>/")
def check(id):
	result = celery.AsyncResult(id)
	status = result.status
	traceback = result.traceback
	result = result.result

	if isinstance(result, Exception):
		info = {
				'id': id,
				'status': status,
			}

		if current_user.is_authenticated and current_user.rank.at_least(UserRank.ADMIN):
			info["error"] = str(traceback)
		elif str(result)[1:12] == "TaskError: ":
			if hasattr(result, "value"):
				info["error"] = result.value
			else:
				info["error"] = str(result)
		else:
			info["error"] = "Unknown server error"
	else:
		info = {
				'id': id,
				'status': status,
				'result': result,
			}

	if should_return_json():
		return jsonify(info)
	else:
		r = request.args.get("r")
		if r is not None and status == "SUCCESS":
			return redirect(r)
		else:
			return render_template("tasks/view.html", info=info)
