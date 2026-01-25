# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
from flask import render_template, request, abort, redirect, url_for, jsonify

from . import bp
from app.logic.approval_stats import get_approval_statistics
from app.models import UserRank
from app.utils.user import rank_required


@bp.route("/admin/approval_stats/")
@rank_required(UserRank.APPROVER)
def approval_stats():
	start = request.args.get("start")
	end = request.args.get("end")
	if start and end:
		try:
			start = datetime.datetime.fromisoformat(start)
			end = datetime.datetime.fromisoformat(end)
		except ValueError:
			abort(400)
	elif start:
		return redirect(url_for("admin.approval_stats", start=start, end=datetime.datetime.utcnow().date().isoformat()))
	elif end:
		return redirect(url_for("admin.approval_stats", start="2020-07-01", end=end))
	else:
		end = datetime.datetime.utcnow()
		start = end - datetime.timedelta(days=365)

	stats = get_approval_statistics(start, end)
	return render_template("admin/approval_stats.html", stats=stats, start=start, end=end)


@bp.route("/admin/approval_stats.json")
@rank_required(UserRank.APPROVER)
def approval_stats_json():
	start = request.args.get("start")
	end = request.args.get("end")
	if start and end:
		try:
			start = datetime.datetime.fromisoformat(start)
			end = datetime.datetime.fromisoformat(end)
		except ValueError:
			abort(400)
	else:
		end = datetime.datetime.utcnow()
		start = end - datetime.timedelta(days=365)

	stats = get_approval_statistics(start, end)
	for key, value in stats.packages_info.items():
		stats.packages_info[key] = value.__dict__()

	return jsonify({
		"start": start.isoformat(),
		"end": end.isoformat(),
		"editor_approvals": stats.editor_approvals,
		"packages_info": stats.packages_info,
		"turnaround_time": {
			"avg": stats.avg_turnaround_time,
			"max": stats.max_turnaround_time,
		},
	})
