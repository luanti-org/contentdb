# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

from flask import Blueprint, render_template

from app.domain.approval_stats import get_public_approval_statistics
from app.models import UserRank
from app.utils.user import rank_required

bp = Blueprint("stats", __name__)


@bp.route("/stats/approval/")
@rank_required(UserRank.APPROVER)
def approval():
	stats = get_public_approval_statistics()
	return render_template("stats/approval.html", stats=stats)
