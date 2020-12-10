# ContentDB
# Copyright (C) 2018-20  rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import datetime
import enum

from flask_login import UserMixin
from sqlalchemy import desc, text

from app import gravatar
from . import db


class UserRank(enum.Enum):
	BANNED         = 0
	NOT_JOINED     = 1
	NEW_MEMBER     = 2
	MEMBER         = 3
	TRUSTED_MEMBER = 4
	EDITOR         = 5
	MODERATOR      = 6
	ADMIN          = 7

	def atLeast(self, min):
		return self.value >= min.value

	def getTitle(self):
		return self.name.replace("_", " ").title()

	def toName(self):
		return self.name.lower()

	def __str__(self):
		return self.name

	@classmethod
	def choices(cls):
		return [(choice, choice.getTitle()) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == UserRank else UserRank[item]


class Permission(enum.Enum):
	EDIT_PACKAGE       = "EDIT_PACKAGE"
	APPROVE_CHANGES    = "APPROVE_CHANGES"
	DELETE_PACKAGE     = "DELETE_PACKAGE"
	CHANGE_AUTHOR      = "CHANGE_AUTHOR"
	CHANGE_NAME        = "CHANGE_NAME"
	MAKE_RELEASE       = "MAKE_RELEASE"
	DELETE_RELEASE     = "DELETE_RELEASE"
	ADD_SCREENSHOTS    = "ADD_SCREENSHOTS"
	REIMPORT_META      = "REIMPORT_META"
	APPROVE_SCREENSHOT = "APPROVE_SCREENSHOT"
	APPROVE_RELEASE    = "APPROVE_RELEASE"
	APPROVE_NEW        = "APPROVE_NEW"
	EDIT_TAGS          = "EDIT_TAGS"
	CREATE_TAG         = "CREATE_TAG"
	CHANGE_RELEASE_URL = "CHANGE_RELEASE_URL"
	CHANGE_USERNAMES   = "CHANGE_USERNAMES"
	CHANGE_RANK        = "CHANGE_RANK"
	CHANGE_EMAIL       = "CHANGE_EMAIL"
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
	CHANGE_PROFILE_URLS = "CHANGE_PROFILE_URLS"

	# Only return true if the permission is valid for *all* contexts
	# See Package.checkPerm for package-specific contexts
	def check(self, user):
		if not user.is_authenticated:
			return False

		if self == Permission.APPROVE_NEW or \
				self == Permission.APPROVE_CHANGES    or \
				self == Permission.APPROVE_RELEASE    or \
				self == Permission.APPROVE_SCREENSHOT or \
				self == Permission.EDIT_TAGS or \
				self == Permission.CREATE_TAG or \
				self == Permission.SEE_THREAD:
			return user.rank.atLeast(UserRank.EDITOR)
		else:
			raise Exception("Non-global permission checked globally. Use Package.checkPerm or User.checkPerm instead.")

	@staticmethod
	def checkPerm(user, perm):
		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to Permission.check")

		return perm.check(user)

def display_name_default(context):
	return context.get_current_parameters()["username"]

class User(db.Model, UserMixin):
	id           = db.Column(db.Integer, primary_key=True)

	# User authentication information
	username     = db.Column(db.String(50, collation="NOCASE"), nullable=False, unique=True, index=True)
	password     = db.Column(db.String(255), nullable=True, server_default=None)
	reset_password_token = db.Column(db.String(100), nullable=False, server_default="")

	def get_id(self):
		return self.username

	rank         = db.Column(db.Enum(UserRank))

	# Account linking
	github_username = db.Column(db.String(50, collation="NOCASE"), nullable=True, unique=True)
	forums_username = db.Column(db.String(50, collation="NOCASE"), nullable=True, unique=True)

	# Access token for webhook setup
	github_access_token = db.Column(db.String(50), nullable=True, server_default=None)

	# User email information
	email         = db.Column(db.String(255), nullable=True, unique=True)
	email_confirmed_at  = db.Column(db.DateTime())

	# User information
	profile_pic   = db.Column(db.String(255), nullable=True, server_default=None)
	is_active     = db.Column("is_active", db.Boolean, nullable=False, server_default="0")
	display_name  = db.Column(db.String(100), nullable=False, default=display_name_default)

	# Links
	website_url   = db.Column(db.String(255), nullable=True, default=None)
	donate_url    = db.Column(db.String(255), nullable=True, default=None)

	# Content
	notifications = db.relationship("Notification", foreign_keys="Notification.user_id",
			order_by=desc(text("Notification.created_at")), back_populates="user", cascade="all, delete, delete-orphan")
	caused_notifications = db.relationship("Notification", foreign_keys="Notification.causer_id",
			back_populates="causer", cascade="all, delete, delete-orphan", lazy="dynamic")
	notification_preferences = db.relationship("UserNotificationPreferences", uselist=False, back_populates="user",
			cascade="all, delete, delete-orphan")

	audit_log_entries = db.relationship("AuditLogEntry", foreign_keys="AuditLogEntry.causer_id", back_populates="causer",
			order_by=desc("audit_log_entry_created_at"), lazy="dynamic")

	packages      = db.relationship("Package", back_populates="author", lazy="dynamic")
	reviews       = db.relationship("PackageReview", back_populates="author", order_by=db.desc("package_review_created_at"), cascade="all, delete, delete-orphan")
	tokens        = db.relationship("APIToken", back_populates="owner", lazy="dynamic", cascade="all, delete, delete-orphan")
	threads       = db.relationship("Thread", back_populates="author", lazy="dynamic", cascade="all, delete, delete-orphan")
	replies       = db.relationship("ThreadReply", back_populates="author", lazy="dynamic", cascade="all, delete, delete-orphan")

	def __init__(self, username=None, active=False, email=None, password=None):
		self.username = username
		self.email_confirmed_at = datetime.datetime.now() - datetime.timedelta(days=6000)
		self.display_name = username
		self.is_active = active
		self.email = email
		self.password = password
		self.rank = UserRank.NOT_JOINED

	def canAccessTodoList(self):
		return Permission.APPROVE_NEW.check(self) or \
				Permission.APPROVE_RELEASE.check(self) or \
				Permission.APPROVE_CHANGES.check(self)

	def isClaimed(self):
		return self.rank.atLeast(UserRank.NEW_MEMBER)

	def getProfilePicURL(self):
		if self.profile_pic:
			return self.profile_pic
		else:
			return gravatar(self.email or "")

	def checkPerm(self, user, perm):
		if not user.is_authenticated:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to User.checkPerm()")

		# Members can edit their own packages, and editors can edit any packages
		if perm == Permission.CHANGE_AUTHOR:
			return user.rank.atLeast(UserRank.EDITOR)
		elif perm == Permission.CHANGE_RANK or perm == Permission.CHANGE_USERNAMES:
			return user.rank.atLeast(UserRank.MODERATOR)
		elif perm == Permission.CHANGE_EMAIL or perm == Permission.CHANGE_PROFILE_URLS:
			return user == self or user.rank.atLeast(UserRank.ADMIN)
		elif perm == Permission.CREATE_TOKEN:
			if user == self:
				return user.rank.atLeast(UserRank.MEMBER)
			else:
				return user.rank.atLeast(UserRank.MODERATOR) and user.rank.atLeast(self.rank)
		else:
			raise Exception("Permission {} is not related to users".format(perm.name))

	def canCommentRL(self):
		factor = 1
		if self.rank.atLeast(UserRank.ADMIN):
			return True
		elif self.rank.atLeast(UserRank.TRUSTED_MEMBER):
			factor *= 2

		one_min_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
		if ThreadReply.query.filter_by(author=self) \
				.filter(ThreadReply.created_at > one_min_ago).count() >= 3 * factor:
			return False

		hour_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
		if ThreadReply.query.filter_by(author=self) \
				.filter(ThreadReply.created_at > hour_ago).count() >= 20 * factor:
			return False

		return True

	def canOpenThreadRL(self):
		factor = 1
		if self.rank.atLeast(UserRank.ADMIN):
			return True
		elif self.rank.atLeast(UserRank.TRUSTED_MEMBER):
			factor *= 5

		hour_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
		return Thread.query.filter_by(author=self) \
			.filter(Thread.created_at > hour_ago).count() < 2 * factor

	def __eq__(self, other):
		if other is None:
			return False

		if not self.is_authenticated or not other.is_authenticated:
			return False

		assert self.id > 0
		return self.id == other.id

	def can_see_edit_profile(self, current_user):
		return self.checkPerm(current_user, Permission.CHANGE_USERNAMES) or \
			self.checkPerm(current_user, Permission.CHANGE_EMAIL) or \
			self.checkPerm(current_user, Permission.CHANGE_RANK)

	def can_delete(self):
		return self.packages.count() == 0 and ForumTopic.query.filter_by(author=self).count() == 0


class UserEmailVerification(db.Model):
	id      = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	email   = db.Column(db.String(100))
	token   = db.Column(db.String(32))
	user    = db.relationship("User", foreign_keys=[user_id])
	is_password_reset = db.Column(db.Boolean, nullable=False, default=False)


class EmailSubscription(db.Model):
	id          = db.Column(db.Integer, primary_key=True)
	email       = db.Column(db.String(100), nullable=False, unique=True)
	blacklisted = db.Column(db.Boolean, nullable=False, default=False)
	token       = db.Column(db.String(32), nullable=True, default=None)

	def __init__(self, email):
		self.email = email
		self.blacklisted = False
		self.token = None


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

	# Added / removed as maintainer
	MAINTAINER     = 6

	# Editor misc
	EDITOR_ALERT   = 7

	# Editor misc
	EDITOR_MISC    = 8

	# Any other
	OTHER          = 0


	def getTitle(self):
		return self.name.replace("_", " ").title()

	def toName(self):
		return self.name.lower()

	def get_description(self):
		if self == NotificationType.PACKAGE_EDIT:
			return "When another user edits your packages, releases, etc."
		elif self == NotificationType.PACKAGE_APPROVAL:
			return "Notifications from editors related to the package approval process."
		elif self == NotificationType.NEW_THREAD:
			return "When a thread is created on your package."
		elif self == NotificationType.NEW_REVIEW:
			return "When a user posts a review on your package."
		elif self == NotificationType.THREAD_REPLY:
			return "When someone replies to a thread you're watching."
		elif self == NotificationType.MAINTAINER:
			return "When your package's maintainers change."
		elif self == NotificationType.EDITOR_ALERT:
			return "For editors: Important alerts."
		elif self == NotificationType.EDITOR_MISC:
			return "For editors: Minor notifications, including new threads."
		elif self == NotificationType.OTHER:
			return "Minor notifications not important enough for a dedicated category."
		else:
			return ""

	def __str__(self):
		return self.name

	def __lt__(self, other):
		return self.value < other.value

	@classmethod
	def choices(cls):
		return [(choice, choice.getTitle()) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == NotificationType else NotificationType[item]


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
	package    = db.relationship("Package", foreign_keys=[package_id])

	created_at = db.Column(db.DateTime, nullable=True, default=datetime.datetime.utcnow)

	def __init__(self, user, causer, type, title, url, package=None):
		if len(title) > 100:
			title = title[:99] + "…"

		self.user    = user
		self.causer  = causer
		self.type    = type
		self.title   = title
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
		self.pref_maintainer = 1
		self.pref_editor_alert = 1
		self.pref_editor_misc = 0
		self.pref_other = 0

	def get_can_email(self, notification_type):
		return getattr(self, "pref_" + notification_type.toName()) == 2

	def set_can_email(self, notification_type, value):
		value = 2 if value else 0
		setattr(self, "pref_" + notification_type.toName(), value)

	def get_can_digest(self, notification_type):
		return getattr(self, "pref_" + notification_type.toName()) >= 1

	def set_can_digest(self, notification_type, value):
		if self.get_can_email(notification_type):
			return

		value = 1 if value else 0
		setattr(self, "pref_" + notification_type.toName(), value)
