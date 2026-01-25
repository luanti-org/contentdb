# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import enum

from flask import current_app
from flask_babel import lazy_gettext
from flask_login import UserMixin
from sqlalchemy import desc, text

from . import db
from app.utils.misc import truncate_string
from app.utils.flask import abs_url_for


class UserRank(enum.Enum):
	BANNED         = 0
	NOT_JOINED     = 1
	NEW_MEMBER     = 2
	MEMBER         = 3
	TRUSTED_MEMBER = 4
	APPROVER       = 5
	EDITOR         = 6
	BOT            = 7
	MODERATOR      = 8
	ADMIN          = 9

	def at_least(self, min):
		return self.value >= min.value

	@property
	def title(self):
		if self == UserRank.BANNED:
			return lazy_gettext("Banned")
		elif self == UserRank.NOT_JOINED:
			return lazy_gettext("Not Joined")
		elif self == UserRank.NEW_MEMBER:
			return lazy_gettext("New Member")
		elif self == UserRank.MEMBER:
			return lazy_gettext("Member")
		elif self == UserRank.TRUSTED_MEMBER:
			return lazy_gettext("Trusted Member")
		elif self == UserRank.APPROVER:
			return lazy_gettext("Approver")
		elif self == UserRank.EDITOR:
			return lazy_gettext("Editor")
		elif self == UserRank.BOT:
			return lazy_gettext("Bot")
		elif self == UserRank.MODERATOR:
			return lazy_gettext("Moderator")
		elif self == UserRank.ADMIN:
			return lazy_gettext("Admin")

	def to_name(self):
		return self.name.lower()

	def __str__(self):
		return self.name

	@classmethod
	def choices(cls):
		return [(choice, choice.title) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == UserRank else UserRank[item.upper()]


class Permission(enum.Enum):
	VIEW_PACKAGE       = "VIEW_PACKAGE"
	EDIT_PACKAGE       = "EDIT_PACKAGE"
	DELETE_PACKAGE     = "DELETE_PACKAGE"
	CHANGE_AUTHOR      = "CHANGE_AUTHOR"
	CHANGE_NAME        = "CHANGE_NAME"
	MAKE_RELEASE       = "MAKE_RELEASE"
	DELETE_RELEASE     = "DELETE_RELEASE"
	ADD_SCREENSHOTS    = "ADD_SCREENSHOTS"
	APPROVE_SCREENSHOT = "APPROVE_SCREENSHOT"
	APPROVE_RELEASE    = "APPROVE_RELEASE"
	APPROVE_NEW        = "APPROVE_NEW"
	EDIT_TAGS          = "EDIT_TAGS"
	CREATE_TAG         = "CREATE_TAG"
	CHANGE_RELEASE_URL = "CHANGE_RELEASE_URL"
	CHANGE_USERNAMES   = "CHANGE_USERNAMES"
	CHANGE_RANK        = "CHANGE_RANK"
	CHANGE_EMAIL       = "CHANGE_EMAIL"
	LINK_TO_WEBSITE    = "LINK_TO_WEBSITE"
	SEE_THREAD         = "SEE_THREAD"
	CREATE_THREAD      = "CREATE_THREAD"
	COMMENT_THREAD     = "COMMENT_THREAD"
	LOCK_THREAD        = "LOCK_THREAD"
	DELETE_THREAD      = "DELETE_THREAD"
	DELETE_REPLY       = "DELETE_REPLY"
	EDIT_REPLY         = "EDIT_REPLY"
	UNAPPROVE_PACKAGE  = "UNAPPROVE_PACKAGE"
	TOPIC_DISCARD      = "TOPIC_DISCARD"
	CREATE_TOKEN       = "CREATE_TOKEN"
	EDIT_MAINTAINERS   = "EDIT_MAINTAINERS"
	DELETE_REVIEW      = "DELETE_REVIEW"
	CHANGE_PROFILE_URLS = "CHANGE_PROFILE_URLS"
	CHANGE_DISPLAY_NAME = "CHANGE_DISPLAY_NAME"
	VIEW_AUDIT_DESCRIPTION = "VIEW_AUDIT_DESCRIPTION"
	EDIT_COLLECTION = "EDIT_COLLECTION"
	VIEW_COLLECTION = "VIEW_COLLECTION"
	CREATE_OAUTH_CLIENT = "CREATE_OAUTH_CLIENT"
	SEE_REPORT = "SEE_REPORT"

	# Only return true if the permission is valid for *all* contexts
	# See Package.check_perm for package-specific contexts
	def check(self, user):
		if not user.is_authenticated:
			return False

		if self == Permission.APPROVE_NEW or \
				self == Permission.APPROVE_RELEASE    or \
				self == Permission.APPROVE_SCREENSHOT or \
				self == Permission.SEE_THREAD:
			return user.rank.at_least(UserRank.APPROVER)

		elif self == Permission.EDIT_TAGS or self == Permission.CREATE_TAG:
			return user.rank.at_least(UserRank.EDITOR)

		else:
			raise Exception("Non-global permission checked globally. Use Package.check_perm or User.check_perm instead.")

	@staticmethod
	def check_perm(user, perm):
		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to Permission.check")

		return perm.check(user)


def display_name_default(context):
	return context.get_current_parameters()["username"]


class User(db.Model, UserMixin):
	id           = db.Column(db.Integer, primary_key=True)

	created_at = db.Column(db.DateTime, nullable=True, default=datetime.datetime.utcnow)

	# User authentication information
	username     = db.Column(db.String(50, collation="NOCASE"), nullable=False, unique=True, index=True)
	password     = db.Column(db.String(255), nullable=True, server_default=None)
	reset_password_token = db.Column(db.String(100), nullable=False, server_default="")

	def get_id(self):
		return self.username

	rank         = db.Column(db.Enum(UserRank), nullable=False)

	# Account linking
	github_username = db.Column(db.String(50, collation="NOCASE"), nullable=True, unique=True)
	github_user_id = db.Column(db.Integer, nullable=True, unique=True)
	forums_username = db.Column(db.String(50, collation="NOCASE"), nullable=True, unique=True)

	# Access token for webhook setup
	github_access_token = db.Column(db.String(50), nullable=True, server_default=None)

	# User email information
	email         = db.Column(db.String(255), nullable=True, unique=True)
	email_confirmed_at  = db.Column(db.DateTime(), nullable=True, server_default=None)

	locale = db.Column(db.String(10), nullable=True, default=None)

	# User information
	profile_pic   = db.Column(db.String(255), nullable=True, server_default=None)
	is_active     = db.Column("is_active", db.Boolean, nullable=False, server_default="0")
	display_name  = db.Column(db.String(100), nullable=False, default=display_name_default)

	# Links
	website_url   = db.Column(db.String(255), nullable=True, default=None)
	donate_url    = db.Column(db.String(255), nullable=True, default=None)

	# Content
	notifications = db.relationship("Notification", foreign_keys="Notification.user_id", lazy="dynamic",
									order_by=desc(text("Notification.created_at")), back_populates="user", cascade="all, delete, delete-orphan")
	caused_notifications = db.relationship("Notification", foreign_keys="Notification.causer_id",
										   back_populates="causer", cascade="all, delete, delete-orphan", lazy="dynamic")
	notification_preferences = db.relationship("UserNotificationPreferences", uselist=False, back_populates="user",
											   cascade="all, delete, delete-orphan")

	email_verifications = db.relationship("UserEmailVerification", foreign_keys="UserEmailVerification.user_id",
										  back_populates="user", cascade="all, delete, delete-orphan", lazy="dynamic")

	audit_log_entries = db.relationship("AuditLogEntry", foreign_keys="AuditLogEntry.causer_id", back_populates="causer",
										order_by=desc("audit_log_entry_created_at"), lazy="dynamic")

	maintained_packages = db.relationship("Package", lazy="dynamic", secondary="maintainers", order_by=db.asc("package_title"))

	packages      = db.relationship("Package", back_populates="author", lazy="dynamic", order_by=db.asc("package_title"))
	reviews       = db.relationship("PackageReview", back_populates="author", order_by=db.desc("package_review_created_at"), cascade="all, delete, delete-orphan")
	review_votes  = db.relationship("PackageReviewVote", back_populates="user", cascade="all, delete, delete-orphan")
	tokens        = db.relationship("APIToken", back_populates="owner", lazy="dynamic", cascade="all, delete, delete-orphan")
	threads       = db.relationship("Thread", back_populates="author", lazy="dynamic", cascade="all, delete, delete-orphan")
	replies       = db.relationship("ThreadReply", back_populates="author", lazy="dynamic", cascade="all, delete, delete-orphan", order_by=db.desc("created_at"))
	forum_topics  = db.relationship("ForumTopic", back_populates="author", lazy="dynamic", cascade="all, delete, delete-orphan")
	collections = db.relationship("Collection", back_populates="author", lazy="dynamic", cascade="all, delete, delete-orphan", order_by=db.asc("title"))
	clients = db.relationship("OAuthClient", back_populates="owner", lazy="dynamic", cascade="all, delete, delete-orphan")
	reports = db.relationship("Report", back_populates="user", lazy="dynamic", cascade="all")

	ban = db.relationship("UserBan", foreign_keys="UserBan.user_id", back_populates="user", uselist=False)

	@property
	def is_banned(self):
		return (self.ban and not self.ban.has_expired) or self.rank == UserRank.BANNED

	def get_dict(self):
		from app.utils.flask import abs_url_for
		return {
			"username": self.username,
			"display_name": self.display_name,
			"rank": self.rank.name.lower(),
			"profile_pic_url": self.profile_pic,
			"website_url": self.website_url,
			"donate_url": self.donate_url,
			"connections": {
				"github": self.github_username,
				"forums": self.forums_username,
			},
			"links": {
				"api_packages": abs_url_for("api.packages", author=self.username),
				"profile": abs_url_for("users.profile", username=self.username),
			}
		}

	def __init__(self, username=None, active=False, email=None, password=None):
		self.username = username
		self.display_name = username
		self.is_active = active
		self.email = email
		self.password = password
		self.rank = UserRank.NOT_JOINED

	def can_access_todo_list(self):
		return Permission.APPROVE_NEW.check(self) or Permission.APPROVE_RELEASE.check(self)

	def get_profile_pic_url(self, absolute: bool = False):
		if self.profile_pic:
			if absolute:
				return current_app.config["BASE_URL"] + self.profile_pic
			else:
				return self.profile_pic
		elif self.rank == UserRank.BOT:
			if absolute:
				return current_app.config["BASE_URL"] + "/static/bot_avatar.png"
			else:
				return "/static/bot_avatar.png"
		else:
			from app.utils.gravatar import get_gravatar
			return get_gravatar(self.email or f"{self.username}@content.luanti.org")

	def check_perm(self, user, perm):
		if user is None or not user.is_authenticated:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to User.check_perm()")

		# Members can edit their own packages, and editors can edit any packages
		if perm == Permission.CHANGE_AUTHOR:
			return user.rank.at_least(UserRank.EDITOR)
		elif perm == Permission.CHANGE_USERNAMES:
			return user.rank.at_least(UserRank.MODERATOR)
		elif perm == Permission.CHANGE_RANK:
			return user.rank.at_least(UserRank.MODERATOR) and not self.rank.at_least(user.rank)
		elif perm == Permission.CHANGE_EMAIL or perm == Permission.CHANGE_PROFILE_URLS:
			return user == self or (user.rank.at_least(UserRank.MODERATOR) and not self.rank.at_least(user.rank))
		elif perm == Permission.CHANGE_DISPLAY_NAME:
			return user.rank.at_least(UserRank.NEW_MEMBER if user == self else UserRank.MODERATOR)
		elif perm == Permission.CREATE_TOKEN or perm == Permission.CREATE_OAUTH_CLIENT:
			if user == self:
				return user.rank.at_least(UserRank.NEW_MEMBER)
			else:
				return user.rank.at_least(UserRank.MODERATOR) and user.rank.at_least(self.rank)
		elif perm == Permission.LINK_TO_WEBSITE:
			return user.rank.at_least(UserRank.MEMBER)
		else:
			raise Exception("Permission {} is not related to users".format(perm.name))

	def can_comment_ratelimit(self):
		from app.models import ThreadReply

		factor = 1
		if self.rank.at_least(UserRank.ADMIN):
			return True
		elif self.rank.at_least(UserRank.TRUSTED_MEMBER):
			factor = 3
		elif self.rank.at_least(UserRank.MEMBER):
			factor = 2

		one_min_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
		if ThreadReply.query.filter_by(author=self) \
				.filter(ThreadReply.created_at > one_min_ago, ThreadReply.is_status_update == False).count() >= 2 * factor:
			return False

		hour_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
		if ThreadReply.query.filter_by(author=self) \
				.filter(ThreadReply.created_at > hour_ago, ThreadReply.is_status_update == False).count() >= 10 * factor:
			return False

		return True

	def can_open_thread_ratelimit(self):
		from app.models import Thread

		factor = 1
		if self.rank.at_least(UserRank.ADMIN):
			return True
		elif self.rank.at_least(UserRank.TRUSTED_MEMBER):
			factor = 5
		elif self.rank.at_least(UserRank.MEMBER):
			factor = 2

		hour_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
		return Thread.query.filter_by(author=self)\
				.filter(Thread.created_at > hour_ago).count() < 2 * factor

	def can_review_ratelimit(self):
		from app.models import PackageReview

		factor = 1
		if self.rank.at_least(UserRank.ADMIN):
			return True
		elif self.rank.at_least(UserRank.TRUSTED_MEMBER):
			factor *= 5

		five_mins_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
		if PackageReview.query.filter_by(author=self) \
				.filter(PackageReview.created_at > five_mins_ago).count() > 2 * factor:
			return False

		hour_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
		return PackageReview.query.filter_by(author=self) \
				.filter(PackageReview.created_at > hour_ago).count() < 10 * factor

	def __eq__(self, other):
		if other is None:
			return False

		# Anonymous users
		if not hasattr(self, "id") or not hasattr(other, "id"):
			return False

		assert self.id > 0
		return self.id == other.id

	def can_see_edit_profile(self, current_user):
		return self.check_perm(current_user, Permission.CHANGE_USERNAMES) or \
				self.check_perm(current_user, Permission.CHANGE_EMAIL) or \
				self.check_perm(current_user, Permission.CHANGE_RANK)

	def can_delete(self):
		from app.models import ForumTopic
		return self.packages.count() == 0 and \
			ForumTopic.query.filter_by(author=self).count() == 0 and \
			self.rank != UserRank.BANNED


class UserEmailVerification(db.Model):
	id      = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	email   = db.Column(db.String(100), nullable=False)
	token   = db.Column(db.String(32), nullable=True)
	user    = db.relationship("User", foreign_keys=[user_id], back_populates="email_verifications")
	is_password_reset = db.Column(db.Boolean, nullable=False, default=False)
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	@property
	def is_expired(self):
		delta = (datetime.datetime.now() - self.created_at)
		delta: datetime.timedelta
		return delta.total_seconds() > 12 * 60 * 60


class EmailSubscription(db.Model):
	id          = db.Column(db.Integer, primary_key=True)
	email       = db.Column(db.String(100), nullable=False, unique=True)
	blacklisted = db.Column(db.Boolean, nullable=False, default=False)
	token       = db.Column(db.String(32), nullable=True, default=None)

	def __init__(self, email):
		self.email = email
		self.blacklisted = False
		self.token = None

	@property
	def url(self):
		return abs_url_for('users.unsubscribe', token=self.token)


class NotificationType(enum.Enum):
	# Package / release / etc
	PACKAGE_EDIT   = 1

	# Approval review actions
	PACKAGE_APPROVAL = 2

	# New thread
	NEW_THREAD     = 3

	# New Review
	NEW_REVIEW     = 4

	# Posted reply to subscribed thread
	THREAD_REPLY   = 5

	# A bot notification
	BOT            = 6

	# Added / removed as maintainer
	MAINTAINER     = 7

	# Editor misc
	EDITOR_ALERT   = 8

	# Editor misc
	EDITOR_MISC    = 9

	# Any other
	OTHER          = 0

	@property
	def title(self):
		if self == NotificationType.PACKAGE_EDIT:
			# NOTE: PACKAGE_EDIT notification type
			return lazy_gettext("Package Edit")
		elif self == NotificationType.PACKAGE_APPROVAL:
			# NOTE: PACKAGE_APPROVAL notification type
			return lazy_gettext("Package Approval")
		elif self == NotificationType.NEW_THREAD:
			# NOTE: NEW_THREAD notification type
			return lazy_gettext("New Thread")
		elif self == NotificationType.NEW_REVIEW:
			# NOTE: NEW_REVIEW notification type
			return lazy_gettext("New Review")
		elif self == NotificationType.THREAD_REPLY:
			# NOTE: THREAD_REPLY notification type
			return lazy_gettext("Thread Reply")
		elif self == NotificationType.BOT:
			# NOTE: BOT notification type
			return lazy_gettext("Bot")
		elif self == NotificationType.MAINTAINER:
			# NOTE: MAINTAINER notification type
			return lazy_gettext("Maintainer")
		elif self == NotificationType.EDITOR_ALERT:
			# NOTE: EDITOR_ALERT notification type
			return lazy_gettext("Editor Alert")
		elif self == NotificationType.EDITOR_MISC:
			# NOTE: EDITOR_MISC notification type
			return lazy_gettext("Editor Misc")
		elif self == NotificationType.OTHER:
			# NOTE: OTHER notification type
			return lazy_gettext("Other")
		else:
			raise "Unknown notification type"

	def to_name(self):
		return self.name.lower()

	@property
	def this_is(self):
		if self == NotificationType.PACKAGE_EDIT:
			return lazy_gettext("This is a Package Edit notification.")
		elif self == NotificationType.PACKAGE_APPROVAL:
			return lazy_gettext("This is a Package Approval notification.")
		elif self == NotificationType.NEW_THREAD:
			return lazy_gettext("This is a New Thread notification.")
		elif self == NotificationType.NEW_REVIEW:
			return lazy_gettext("This is a New Review notification.")
		elif self == NotificationType.THREAD_REPLY:
			return lazy_gettext("This is a Thread Reply notification.")
		elif self == NotificationType.BOT:
			return lazy_gettext("This is a Bot notification.")
		elif self == NotificationType.MAINTAINER:
			return lazy_gettext("This is a Maintainer change notification.")
		elif self == NotificationType.EDITOR_ALERT:
			return lazy_gettext("This is an Editor Alert notification.")
		elif self == NotificationType.EDITOR_MISC:
			return lazy_gettext("This is an Editor Misc notification.")
		elif self == NotificationType.OTHER:
			return lazy_gettext("This is an Other notification.")
		else:
			raise "Unknown notification type"

	@property
	def description(self):
		if self == NotificationType.PACKAGE_EDIT:
			return lazy_gettext("When another user edits your packages, releases, etc.")
		elif self == NotificationType.PACKAGE_APPROVAL:
			return lazy_gettext("Notifications from editors related to the package approval process.")
		elif self == NotificationType.NEW_THREAD:
			return lazy_gettext("When a thread is created on your package.")
		elif self == NotificationType.NEW_REVIEW:
			return lazy_gettext("When a user posts a review on your package.")
		elif self == NotificationType.THREAD_REPLY:
			return lazy_gettext("When someone replies to a thread you're watching.")
		elif self == NotificationType.BOT:
			return lazy_gettext("From a bot - for example, update notifications.")
		elif self == NotificationType.MAINTAINER:
			return lazy_gettext("When your package's maintainers change.")
		elif self == NotificationType.EDITOR_ALERT:
			return lazy_gettext("For editors: Important alerts.")
		elif self == NotificationType.EDITOR_MISC:
			return lazy_gettext("For editors: Minor notifications, including new threads.")
		elif self == NotificationType.OTHER:
			return lazy_gettext("Minor notifications not important enough for a dedicated category.")
		else:
			raise "Unknown notification type"

	def __str__(self):
		return self.name

	def __lt__(self, other):
		return self.value < other.value

	@classmethod
	def choices(cls):
		return [(choice, choice.title) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == NotificationType else NotificationType[item.upper()]


class Notification(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	user       = db.relationship("User", foreign_keys=[user_id], back_populates="notifications")

	causer_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	causer     = db.relationship("User", foreign_keys=[causer_id], back_populates="caused_notifications")

	type       = db.Column(db.Enum(NotificationType), nullable=False, default=NotificationType.OTHER)

	emailed    = db.Column(db.Boolean(), nullable=False, default=False)

	title      = db.Column(db.String(100), nullable=False)
	url        = db.Column(db.String(200), nullable=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=True)
	package    = db.relationship("Package", foreign_keys=[package_id], back_populates="notifications")

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
	read_at = db.Column(db.DateTime, nullable=True, default=None)

	def __init__(self, user, causer, type, title, url, package=None):
		self.user    = user
		self.causer  = causer
		self.type    = type
		self.title   = title
		self.title   = truncate_string(title, 100)
		self.url     = url
		self.package = package

	def can_send_email(self):
		prefs = self.user.notification_preferences
		return prefs and self.user.email and prefs.get_can_email(self.type)

	def can_send_digest(self):
		prefs = self.user.notification_preferences
		return prefs and self.user.email and prefs.get_can_digest(self.type)


class UserNotificationPreferences(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
	user = db.relationship("User", back_populates="notification_preferences")

	# 2 = immediate emails
	# 1 = daily digest emails
	# 0 = no emails

	pref_package_edit     = db.Column(db.Integer, nullable=False)
	pref_package_approval = db.Column(db.Integer, nullable=False)
	pref_new_thread       = db.Column(db.Integer, nullable=False)
	pref_new_review       = db.Column(db.Integer, nullable=False)
	pref_thread_reply     = db.Column(db.Integer, nullable=False)
	pref_bot              = db.Column(db.Integer, nullable=False)
	pref_maintainer       = db.Column(db.Integer, nullable=False)
	pref_editor_alert     = db.Column(db.Integer, nullable=False)
	pref_editor_misc      = db.Column(db.Integer, nullable=False)
	pref_other            = db.Column(db.Integer, nullable=False)

	def __init__(self, user):
		self.user = user
		self.pref_package_edit = 1
		self.pref_package_approval = 1
		self.pref_new_thread = 1
		self.pref_new_review = 1
		self.pref_thread_reply = 2
		self.pref_bot = 1
		self.pref_maintainer = 1
		self.pref_editor_alert = 1
		self.pref_editor_misc = 0
		self.pref_other = 0

	def get_can_email(self, notification_type):
		return getattr(self, "pref_" + notification_type.to_name()) == 2

	def set_can_email(self, notification_type, value):
		value = 2 if value else 0
		setattr(self, "pref_" + notification_type.to_name(), value)

	def get_can_digest(self, notification_type):
		return getattr(self, "pref_" + notification_type.to_name()) >= 1

	def set_can_digest(self, notification_type, value):
		if self.get_can_email(notification_type):
			return

		value = 1 if value else 0
		setattr(self, "pref_" + notification_type.to_name(), value)


class UserBan(db.Model):
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
	user = db.relationship("User", foreign_keys=[user_id], back_populates="ban")

	message = db.Column(db.UnicodeText, nullable=False)

	banned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
	banned_by = db.relationship("User", foreign_keys=[banned_by_id])

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	expires_at = db.Column(db.DateTime, nullable=True, default=None)

	@property
	def has_expired(self):
		return self.expires_at and datetime.datetime.now() > self.expires_at


class OAuthClient(db.Model):
	__tablename__ = "oauth_client"

	id = db.Column(db.String(24), primary_key=True)
	title = db.Column(db.String(64), unique=True, nullable=False)
	description = db.Column(db.String(300), nullable=True)
	secret = db.Column(db.String(32), nullable=False)
	redirect_url = db.Column(db.String(128), nullable=False)
	approved = db.Column(db.Boolean, nullable=False, default=False)
	verified = db.Column(db.Boolean, nullable=False, default=False)
	is_clientside = db.Column(db.Boolean, nullable=False, default=False)

	owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
	owner = db.relationship("User", foreign_keys=[owner_id], back_populates="clients")

	tokens = db.relationship("APIToken", back_populates="client", lazy="dynamic", cascade="all, delete, delete-orphan")

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	def get_app_type(self):
		return "client" if self.is_clientside else "server"

	def set_app_type(self, value):
		self.is_clientside = value == "client"

	app_type = property(get_app_type, set_app_type)
