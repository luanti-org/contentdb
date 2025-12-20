# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import current_user, login_required
from sqlalchemy import desc

from app.models import db, Notification

bp = Blueprint("notifications", __name__)


@bp.route("/notifications/")
@login_required
def list_all():
	query = (Notification.query.filter(Notification.user == current_user)
			.order_by(desc(Notification.created_at)))

	show_read = request.args.get("read", False)
	if show_read:
		query = query.filter(Notification.read_at.is_not(None))
	else:
		query = query.filter(Notification.read_at.is_(None))

	read_count = Notification.query.filter(Notification.user == current_user, Notification.read_at.is_not(None)).count()
	unread_count = Notification.query.filter(Notification.user == current_user, Notification.read_at.is_(None)).count()

	return render_template("notifications/list.html",
			notifications=query.all(),
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
