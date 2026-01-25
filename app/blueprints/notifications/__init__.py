# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
from itertools import groupby
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import current_user, login_required
from sqlalchemy import desc

from app.models import db, Notification
from app.utils.misc import is_yes

bp = Blueprint("notifications", __name__)


@bp.route("/notifications/")
@login_required
def list_all():
	query = (Notification.query.filter(Notification.user == current_user)
			.order_by(desc(Notification.package_id), desc(Notification.created_at)))

	show_read = is_yes(request.args.get("read", "0"))
	if show_read:
		query = query.filter(Notification.read_at.is_not(None))
	else:
		query = query.filter(Notification.read_at.is_(None))

	read_count = Notification.query.filter(Notification.user == current_user, Notification.read_at.is_not(None)).count()
	unread_count = Notification.query.filter(Notification.user == current_user, Notification.read_at.is_(None)).count()

	notifications = None
	grouped = None

	group = request.args.get("group", "package")
	if group == "package":
		grouped = list(map(lambda x: [x[0], list(x[1])], groupby(query.all(), lambda x: x.package_id)))
		grouped.sort(key=lambda x: x[1][0].created_at, reverse=True)
	else:
		notifications = query.all()

	return render_template("notifications/list.html",
			notifications=notifications, grouped=grouped, group=group,
			show_read=show_read, read_count=read_count, unread_count=unread_count)


@bp.route("/notifications/delete/", methods=["POST"])
@login_required
def delete_all():
	Notification.query.filter_by(user=current_user).delete()
	db.session.commit()
	return redirect(url_for("notifications.list_all"))


@bp.route("/notifications/read/", methods=["POST"])
@login_required
def read_all():
	Notification.query.filter_by(user=current_user).update({"read_at": datetime.datetime.utcnow()})
	db.session.commit()
	return redirect(url_for("notifications.list_all"))
