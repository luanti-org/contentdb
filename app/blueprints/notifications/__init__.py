# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, desc

from app.models import db, Notification, NotificationType

bp = Blueprint("notifications", __name__)


@bp.route("/notifications/")
@login_required
def list_all():
	notifications = Notification.query.filter(Notification.user == current_user,
			Notification.type != NotificationType.EDITOR_ALERT, Notification.type != NotificationType.EDITOR_MISC) \
			.order_by(desc(Notification.created_at)) \
			.all()

	editor_notifications = Notification.query.filter(Notification.user == current_user,
			or_(Notification.type == NotificationType.EDITOR_ALERT, Notification.type == NotificationType.EDITOR_MISC)) \
			.order_by(desc(Notification.created_at)) \
			.all()

	return render_template("notifications/list.html",
			notifications=notifications, editor_notifications=editor_notifications)


@bp.route("/notifications/clear/", methods=["POST"])
@login_required
def clear():
	Notification.query.filter_by(user=current_user).delete()
	db.session.commit()
	return redirect(url_for("notifications.list_all"))
