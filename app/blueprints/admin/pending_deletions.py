# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime

from flask import render_template
from sqlalchemy.orm import joinedload

from app.domain.user_deletion import get_deletion_blocker
from app.models import PendingUserDeletion, UserRank
from app.utils.user import rank_required
from . import bp


@bp.route("/admin/users/pending-deletion/")
@rank_required(UserRank.MODERATOR)
def pending_deletions():
	pending = (PendingUserDeletion.query
		.options(joinedload(PendingUserDeletion.user))
		.order_by(PendingUserDeletion.delete_at.asc(), PendingUserDeletion.user_id.asc())
		.all())

	rows = [{
		"pending": x,
		"user": x.user,
		"blocker": get_deletion_blocker(x.user),
	} for x in pending]

	return render_template("admin/pending_deletions.html", rows=rows, now=datetime.datetime.utcnow())
