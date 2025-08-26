# ContentDB
# Copyright (C) 2018-21 rubenwardy
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

from flask import Blueprint, request, render_template, abort, flash, redirect, url_for
from flask_babel import gettext, lazy_gettext
from sqlalchemy.orm import selectinload

from app.markdown import get_user_mentions, render_markdown
from app.tasks.webhooktasks import post_discord_webhook

bp = Blueprint("threads", __name__)

from flask_login import current_user, login_required
from app.models import Package, db, User, Permission, Thread, UserRank, AuditSeverity, \
	NotificationType, ThreadReply
from app.utils import add_notification, is_yes, add_audit_log, get_system_user, has_blocked_domains, \
	normalize_line_endings
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Length
from app.utils import get_int_or_abort


@bp.route("/threads/")
def list_all():
	query = Thread.query
	if not Permission.SEE_THREAD.check(current_user):
		query = query.filter_by(private=False)

	package = None
	pid = request.args.get("pid")
	if pid:
		pid = get_int_or_abort(pid)
		package = Package.query.get_or_404(pid)
		query = query.filter_by(package=package)

	query = query.filter_by(review_id=None)

	query = query.order_by(db.desc(Thread.created_at))

	page = get_int_or_abort(request.args.get("page"), 1)
	num = min(40, get_int_or_abort(request.args.get("n"), 100))

	pagination = query.paginate(page=page, per_page=num)

	return render_template("threads/list.html", pagination=pagination, threads=pagination.items,
			package=package, noindex=pid)


@bp.route("/threads/<int:id>/subscribe/", methods=["POST"])
@login_required
def subscribe(id):
	thread = Thread.query.get(id)
	if thread is None or not thread.check_perm(current_user, Permission.SEE_THREAD):
		abort(404)

	if current_user in thread.watchers:
		flash(gettext("Already subscribed!"), "success")
	else:
		flash(gettext("Subscribed to thread"), "success")
		thread.watchers.append(current_user)
		db.session.commit()

	return redirect(thread.get_view_url())


@bp.route("/threads/<int:id>/unsubscribe/", methods=["POST"])
@login_required
def unsubscribe(id):
	thread = Thread.query.get(id)
	if thread is None or not thread.check_perm(current_user, Permission.SEE_THREAD):
		abort(404)

	if current_user in thread.watchers:
		flash(gettext("Unsubscribed!"), "success")
		thread.watchers.remove(current_user)
		db.session.commit()
	else:
		flash(gettext("Already not subscribed!"), "success")

	return redirect(thread.get_view_url())


@bp.route("/threads/<int:id>/set-lock/", methods=["POST"])
@login_required
def set_lock(id):
	thread = Thread.query.get(id)
	if thread is None or not thread.check_perm(current_user, Permission.LOCK_THREAD):
		abort(404)

	thread.locked = is_yes(request.args.get("lock"))
	if thread.locked is None:
		abort(400)

	if thread.locked:
		msg = "Locked thread '{}'".format(thread.title)
		flash(gettext("Locked thread"), "success")
	else:
		msg = "Unlocked thread '{}'".format(thread.title)
		flash(gettext("Unlocked thread"), "success")

	add_notification(thread.watchers, current_user, NotificationType.OTHER, msg, thread.get_view_url(), thread.package)
	add_audit_log(AuditSeverity.MODERATION, current_user, msg, thread.get_view_url(), thread.package)

	db.session.commit()

	return redirect(thread.get_view_url())


@bp.route("/threads/<int:id>/delete/", methods=["GET", "POST"])
@login_required
def delete_thread(id):
	thread = Thread.query.get(id)
	if thread is None or not thread.check_perm(current_user, Permission.DELETE_THREAD):
		abort(404)

	if request.method == "GET":
		return render_template("threads/delete_thread.html", thread=thread)

	summary = "\n\n".join([("<{}> {}".format(reply.author.display_name, reply.comment)) for reply in thread.replies])

	msg = "Deleted thread {} by {}".format(thread.title, thread.author.display_name)

	db.session.delete(thread)

	add_audit_log(AuditSeverity.MODERATION, current_user, msg, None, thread.package, summary)

	db.session.commit()

	return redirect(url_for("homepage.home"))


@bp.route("/threads/<int:id>/delete-reply/", methods=["GET", "POST"])
@login_required
def delete_reply(id):
	thread = Thread.query.get(id)
	if thread is None:
		abort(404)

	reply_id = request.args.get("reply")
	if reply_id is None:
		abort(404)

	reply = ThreadReply.query.get(reply_id)
	if reply is None or reply.thread != thread:
		abort(404)

	if thread.first_reply == reply:
		flash(gettext("Cannot delete thread opening post!"), "danger")
		return redirect(thread.get_view_url())

	if not reply.check_perm(current_user, Permission.DELETE_REPLY):
		abort(403)

	if request.method == "GET":
		return render_template("threads/delete_reply.html", thread=thread, reply=reply)

	msg = "Deleted reply by {}".format(reply.author.display_name)
	add_audit_log(AuditSeverity.MODERATION, current_user, msg, thread.get_view_url(), thread.package, reply.comment)

	db.session.delete(reply)
	db.session.commit()

	return redirect(thread.get_view_url())


class CommentForm(FlaskForm):
	comment = TextAreaField(lazy_gettext("Comment"), [InputRequired(), Length(2, 2000)], filters=[normalize_line_endings])
	btn_submit = SubmitField(lazy_gettext("Comment"))


@bp.route("/threads/<int:id>/edit/", methods=["GET", "POST"])
@login_required
def edit_reply(id):
	thread = Thread.query.get(id)
	if thread is None:
		abort(404)

	reply_id = request.args.get("reply")
	if reply_id is None:
		abort(404)

	reply: ThreadReply = ThreadReply.query.get(reply_id)
	if reply is None or reply.thread != thread:
		abort(404)

	if not reply.check_perm(current_user, Permission.EDIT_REPLY):
		abort(403)

	form = CommentForm(formdata=request.form, obj=reply)
	if form.validate_on_submit():
		comment = form.comment.data
		if has_blocked_domains(comment, current_user.username, f"edit to reply {reply.get_url(True)}"):
			flash(gettext("Linking to blocked sites is not allowed"), "danger")
		else:
			msg = "Edited reply by {}".format(reply.author.display_name)
			severity = AuditSeverity.NORMAL if current_user == reply.author else AuditSeverity.MODERATION
			add_notification(reply.author, current_user, NotificationType.OTHER, msg, thread.get_view_url(), thread.package)
			add_audit_log(severity, current_user, msg, thread.get_view_url(), thread.package, reply.comment)

			reply.comment = comment

			db.session.commit()

			return redirect(thread.get_view_url())

	return render_template("threads/edit_reply.html", thread=thread, reply=reply, form=form)


@bp.route("/threads/<int:id>/", methods=["GET", "POST"])
def view(id):
	thread: Thread = Thread.query.get(id)
	if thread is None or not thread.check_perm(current_user, Permission.SEE_THREAD):
		abort(404)

	form = CommentForm(formdata=request.form) if thread.check_perm(current_user, Permission.COMMENT_THREAD) else None

	# Check that title is none to load comments into textarea if redirected from new thread page
	if form and form.validate_on_submit() and request.form.get("title") is None:
		comment = form.comment.data

		if not current_user.can_comment_ratelimit():
			flash(gettext("Please wait before commenting again"), "danger")
			return redirect(thread.get_view_url())

		if has_blocked_domains(comment, current_user.username, f"reply to {thread.get_view_url(True)}"):
			flash(gettext("Linking to blocked sites is not allowed"), "danger")
			return render_template("threads/view.html", thread=thread, form=form)

		reply = ThreadReply()
		reply.author = current_user
		reply.comment = comment
		db.session.add(reply)

		thread.replies.append(reply)
		if current_user not in thread.watchers:
			thread.watchers.append(current_user)

		for mentioned_username in get_user_mentions(render_markdown(comment)):
			mentioned = User.query.filter_by(username=mentioned_username).first()
			if mentioned is None:
				continue

			if not thread.check_perm(mentioned, Permission.SEE_THREAD):
				continue

			msg = "Mentioned by {} in '{}'".format(current_user.display_name, thread.title)
			add_notification(mentioned, current_user, NotificationType.THREAD_REPLY,
							 msg, thread.get_view_url(), thread.package)

			if mentioned not in thread.watchers:
				thread.watchers.append(mentioned)

		msg = "New comment on '{}'".format(thread.title)
		add_notification(thread.watchers, current_user, NotificationType.THREAD_REPLY, msg, thread.get_view_url(), thread.package)

		if thread.author == get_system_user():
			approvers = User.query.filter(User.rank >= UserRank.APPROVER).all()
			add_notification(approvers, current_user, NotificationType.EDITOR_MISC, msg,
							 thread.get_view_url(), thread.package)
			post_discord_webhook.delay(current_user.display_name,
					"Replied to bot messages: {}".format(thread.get_view_url(absolute=True)), True)

		db.session.commit()

		return redirect(thread.get_view_url())

	return render_template("threads/view.html", thread=thread, form=form)


class ThreadForm(FlaskForm):
	title	= StringField(lazy_gettext("Title"), [InputRequired(), Length(3,100)])
	comment = TextAreaField(lazy_gettext("Comment"), [InputRequired(), Length(10, 2000)], filters=[normalize_line_endings])
	btn_submit  = SubmitField(lazy_gettext("Open Thread"))


@bp.route("/threads/new/", methods=["GET", "POST"])
@login_required
def new():
	form = ThreadForm(formdata=request.form)

	package = None
	if "pid" in request.args:
		package = Package.query.get(int(request.args.get("pid")))
		if package is None:
			abort(404)

	if package is None and not current_user.rank.at_least(UserRank.APPROVER):
		abort(404)

	is_review_thread = package and not package.approved
	is_private_thread = is_review_thread

	# Check that user can make the thread
	if package and not package.check_perm(current_user, Permission.CREATE_THREAD):
		flash(gettext("Unable to create thread!"), "danger")
		return redirect(url_for("homepage.home"))

	# Only allow creating one thread when not approved
	elif is_review_thread and package.review_thread is not None:
		# Redirect submit to `view` page, which checks for `title` in the form data and so won't commit the reply
		flash(gettext("An approval thread already exists! Consider replying there instead"), "danger")
		return redirect(package.review_thread.get_view_url(), code=307)

	elif not current_user.can_open_thread_ratelimit():
		flash(gettext("Please wait before opening another thread"), "danger")

		if package:
			return redirect(package.get_url("packages.view"))
		else:
			return redirect(url_for("homepage.home"))

	# Set default values
	elif request.method == "GET":
		form.title.data   = request.args.get("title") or ""

	# Validate and submit
	elif form.validate_on_submit():
		if has_blocked_domains(form.comment.data, current_user.username, f"new thread"):
			flash(gettext("Linking to blocked sites is not allowed"), "danger")
		else:
			thread = Thread()
			thread.author  = current_user
			thread.title   = form.title.data
			thread.private = is_private_thread
			thread.package = package
			db.session.add(thread)

			thread.watchers.append(current_user)
			if package and package.author != current_user:
				thread.watchers.append(package.author)

			reply = ThreadReply()
			reply.thread  = thread
			reply.author  = current_user
			reply.comment = form.comment.data
			db.session.add(reply)

			thread.replies.append(reply)

			db.session.commit()

			if is_review_thread:
				package.review_thread = thread

			for mentioned_username in get_user_mentions(render_markdown(form.comment.data)):
				mentioned = User.query.filter_by(username=mentioned_username).first()
				if mentioned is None:
					continue

				msg = "Mentioned by {} in new thread '{}'".format(current_user.display_name, thread.title)
				add_notification(mentioned, current_user, NotificationType.NEW_THREAD,
								 msg, thread.get_view_url(), thread.package)

				if mentioned not in thread.watchers:
					thread.watchers.append(mentioned)

			notif_msg = "New thread '{}'".format(thread.title)
			if package is not None:
				add_notification(package.maintainers, current_user, NotificationType.NEW_THREAD, notif_msg, thread.get_view_url(), package)

			approvers = User.query.filter(User.rank >= UserRank.APPROVER).all()
			add_notification(approvers, current_user, NotificationType.EDITOR_MISC, notif_msg, thread.get_view_url(), package)

			if is_review_thread:
				post_discord_webhook.delay(current_user.display_name,
						"Opened approval thread: {}".format(thread.get_view_url(absolute=True)), True)

			db.session.commit()

			return redirect(thread.get_view_url())

	return render_template("threads/new.html", form=form, package=package)


@bp.route("/users/<username>/comments/")
def user_comments(username):
	user = User.query.filter_by(username=username).first()
	if user is None:
		abort(404)

	page = get_int_or_abort(request.args.get("page"), 1)
	num = min(40, get_int_or_abort(request.args.get("n"), 40))

	# Filter replies the current user can see
	query = ThreadReply.query.options(selectinload(ThreadReply.thread)).filter_by(author=user)
	only_public = False
	if current_user != user and not (current_user.is_authenticated and current_user.rank.at_least(UserRank.APPROVER)):
		query = query.filter(ThreadReply.thread.has(private=False))
		only_public = True

	pagination = query.order_by(db.desc(ThreadReply.created_at)).paginate(page=page, per_page=num)

	return render_template("threads/user_comments.html", user=user, pagination=pagination, only_public=only_public)
