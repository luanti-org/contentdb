# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import smtplib
import typing
from typing import Dict

from flask import render_template
from flask_babel import force_locale, gettext, lazy_gettext, LazyString
from flask_mail import Message
from markupsafe import escape

from app import mail, app
from app.models import Notification, db, EmailSubscription, User
from app.rediscache import increment_key
from app.tasks import celery
from app.utils import abs_url_for, abs_url, random_string


reply_to = app.config.get("MAIL_REPLY_TO", None)


def get_email_subscription(email):
	assert type(email) == str
	ret = EmailSubscription.query.filter_by(email=email).first()
	if not ret:
		ret = EmailSubscription(email)
		ret.token = random_string(32)
		db.session.add(ret)
		db.session.commit()

	return ret


def gen_headers(sub: EmailSubscription) -> Dict[str, str]:
	headers = {
		"List-Help": f"<{abs_url_for('flatpage', path='help/faq/')}>",
		"List-Unsubscribe": f"<{sub.url}>"
	}
	return headers


@celery.task()
def send_verify_email(email, token, locale):
	sub = get_email_subscription(email)
	if sub.blacklisted:
		return

	with force_locale(locale or "en"):
		msg = Message("Confirm email address", recipients=[email], reply_to=reply_to, extra_headers=gen_headers(sub))

		msg.body = """
				This email has been sent to you because someone (hopefully you)
				has entered your email address as a user's email.

				If it wasn't you, then just delete this email.

				If this was you, then please click this link to confirm the address:

				{}
			""".format(abs_url_for('users.verify_email', token=token))

		msg.html = render_template("emails/verify.html", token=token, sub=sub)
		mail.send(msg)
		increment_key("emails_sent")


@celery.task()
def send_unsubscribe_verify(email, locale):
	sub = get_email_subscription(email)
	if sub.blacklisted:
		return

	with force_locale(locale or "en"):
		msg = Message("Confirm unsubscribe", recipients=[email], reply_to=reply_to, extra_headers=gen_headers(sub))

		msg.body = """
					We're sorry to see you go. You just need to do one more thing before your email is blacklisted.
					
					Click this link to blacklist email: {} 
				""".format(abs_url_for('users.unsubscribe', token=sub.token))

		msg.html = render_template("emails/verify_unsubscribe.html", sub=sub)
		mail.send(msg)
		increment_key("emails_sent")


@celery.task(rate_limit="25/m")
def send_email_with_reason(email: str, locale: str, subject: str, text: str, html: str,
		reason: typing.Union[str, LazyString]):
	sub = get_email_subscription(email)
	if sub.blacklisted:
		return

	with force_locale(locale or "en"):
		msg = Message(subject, recipients=[email], reply_to=reply_to, extra_headers=gen_headers(sub))

		msg.body = text
		html = html or f"<pre>{escape(text)}</pre>"
		msg.html = render_template("emails/base.html", subject=subject, content=html, reason=reason, sub=sub)
		mail.send(msg)
		increment_key("emails_sent")


@celery.task(rate_limit="25/m")
def send_user_email(email: str, locale: str, subject: str, text: str, html=None):
	return send_email_with_reason(email, locale, subject, text, html,
			lazy_gettext("You are receiving this email because you are a registered user of ContentDB."))


@celery.task(rate_limit="25/m")
def send_anon_email(email: str, locale: str, subject: str, text: str, html=None):
	return send_email_with_reason(email, locale, subject, text, html,
			lazy_gettext("You are receiving this email because someone (hopefully you) entered your email address as a user's email."))


def send_single_email(notification, locale):
	sub = get_email_subscription(notification.user.email)
	if sub.blacklisted:
		return

	with force_locale(locale or "en"):
		msg = Message(notification.title, recipients=[notification.user.email], reply_to=reply_to, extra_headers=gen_headers(sub))

		msg.body = """
				New notification: {}
				
				View: {}
				
				Manage email settings: {}
				Unsubscribe: {}
			""".format(notification.title, abs_url(notification.url),
						abs_url_for("users.email_notifications", username=notification.user.username),
						abs_url_for("users.unsubscribe", token=sub.token))

		msg.html = render_template("emails/notification.html", notification=notification, sub=sub)
		mail.send(msg)
		increment_key("emails_sent")


def send_notification_digest(notifications: typing.List[Notification], locale):
	user = notifications[0].user

	sub = get_email_subscription(user.email)
	if sub.blacklisted:
		return

	with force_locale(locale or "en"):
		msg = Message(gettext("%(num)d new notifications", num=len(notifications)), reply_to=reply_to, recipients=[user.email], extra_headers=gen_headers(sub))

		msg.body = "".join(["<{}> {}\n{}: {}\n\n".format(notification.causer.display_name, notification.title, gettext("View"), abs_url(notification.url)) for notification in notifications])

		msg.body += "{}: {}\n{}: {}".format(
				gettext("Manage email settings"),
				abs_url_for("users.email_notifications", username=user.username),
				gettext("Unsubscribe"),
				abs_url_for("users.unsubscribe", token=sub.token))

		msg.html = render_template("emails/notification_digest.html", notifications=notifications, user=user, sub=sub)
		mail.send(msg)
		increment_key("emails_sent")


@celery.task()
def send_pending_digests():
	for user in User.query.filter(User.notifications.any(emailed=False)).all():
		to_send = []
		for notification in user.notifications:
			if not notification.emailed and notification.can_send_digest():
				to_send.append(notification)
				notification.emailed = True

		if len(to_send) > 0:
			send_notification_digest(to_send, user.locale or "en")

		db.session.commit()


@celery.task()
def send_pending_notifications():
	for user in User.query.filter(User.notifications.any(emailed=False)).all():
		to_send = []
		for notification in user.notifications:
			if not notification.emailed:
				if notification.can_send_email():
					to_send.append(notification)
					notification.emailed = True
				elif not notification.can_send_digest():
					notification.emailed = True

		db.session.commit()

		try:
			if len(to_send) > 1:
				send_notification_digest(to_send, user.locale or "en")
			elif len(to_send) > 0:
				send_single_email(to_send[0], user.locale or "en")
		except smtplib.SMTPDataError as e:
			if "Message rejected under suspicion of SPAM" in str(e):
				raise Exception(f"Failed to send email to {user.username} due to yandex spam filter") from e
			else:
				raise e
