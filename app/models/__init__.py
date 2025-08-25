# ContentDB
# Copyright (C) 2018-21  rubenwardy
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


from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_searchable import make_searchable

from app import app

# Initialise database

db = SQLAlchemy(app)
migrate = Migrate(app, db)
make_searchable(db.metadata)


from .packages import *
from .users import *
from .threads import *
from .collections import *


class APIToken(db.Model):
	id           = db.Column(db.Integer, primary_key=True)
	access_token = db.Column(db.String(34), unique=True, nullable=False)

	name         = db.Column(db.String(100), nullable=False)

	owner_id     = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	owner        = db.relationship("User", foreign_keys=[owner_id], back_populates="tokens")

	created_at   = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=True)
	package    = db.relationship("Package", foreign_keys=[package_id], back_populates="tokens")

	client_id = db.Column(db.String(24), db.ForeignKey("oauth_client.id"), nullable=True)
	client    = db.relationship("OAuthClient", foreign_keys=[client_id], back_populates="tokens")
	auth_code = db.Column(db.String(34), unique=True, nullable=True)

	def can_operate_on_package(self, package):
		if self.client is not None:
			return False

		if self.package and self.package != package:
			return False

		return package.author == self.owner


class AuditSeverity(enum.Enum):
	NORMAL = 0 # Normal user changes
	USER   = 1 # Security user changes
	EDITOR = 2 # Editor changes
	MODERATION = 3 # Destructive / moderator changes

	def __str__(self):
		return self.name

	@property
	def title(self):
		return self.name.replace("_", " ").title()

	@classmethod
	def choices(cls):
		return [(choice, choice.title) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == AuditSeverity else AuditSeverity[item.upper()]


class AuditLogEntry(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	causer_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
	causer     = db.relationship("User", foreign_keys=[causer_id], back_populates="audit_log_entries")

	severity   = db.Column(db.Enum(AuditSeverity), nullable=False)

	title      = db.Column(db.String(100), nullable=False)
	url        = db.Column(db.String(200), nullable=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=True)
	package    = db.relationship("Package", foreign_keys=[package_id], back_populates="audit_log_entries")

	description = db.Column(db.Text, nullable=True, default=None)

	def __init__(self, causer, severity, title, url, package=None, description=None):
		if len(title) > 100:
			if description is None:
				description = title[99:]
			title = title[:99] + "…"

		self.causer   = causer
		self.severity = severity
		self.title    = title
		self.url      = url
		self.package  = package
		self.description = description

	def check_perm(self, user, perm):
		if not user.is_authenticated:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to AuditLogEntry.check_perm()")

		if perm == Permission.VIEW_AUDIT_DESCRIPTION:
			return user.rank.at_least(UserRank.APPROVER if self.package is not None else UserRank.MODERATOR)
		else:
			raise Exception("Permission {} is not related to audit log entries".format(perm.name))


REPO_BLACKLIST = [".zip", "mediafire.com", "dropbox.com", "weebly.com",
	"minetest.net", "luanti.org", "dropboxusercontent.com", "4shared.com",
	"digitalaudioconcepts.com", "hg.intevation.org", "www.wtfpl.net",
	"imageshack.com", "imgur.com"]


class ForumTopic(db.Model):
	topic_id  = db.Column(db.Integer, primary_key=True, autoincrement=False)

	author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author    = db.relationship("User", back_populates="forum_topics")

	wip       = db.Column(db.Boolean, default=False, nullable=False)
	# TODO: remove
	discarded = db.Column(db.Boolean, default=False, nullable=False)

	type      = db.Column(db.Enum(PackageType), nullable=False)
	title     = db.Column(db.String(200), nullable=False)
	name      = db.Column(db.String(30), nullable=True)
	link      = db.Column(db.String(200), nullable=True)

	posts     = db.Column(db.Integer, nullable=False)
	views     = db.Column(db.Integer, nullable=False)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	@property
	def url(self):
		return "https://forum.luanti.org/viewtopic.php?t=" + str(self.topic_id)

	def get_repo_url(self):
		if self.link is None:
			return None

		for item in REPO_BLACKLIST:
			if item in self.link:
				return None

		return self.link.replace("repo.or.cz/w/", "repo.or.cz/")

	def as_dict(self):
		return {
			"author": self.author.username,
			"name":   self.name,
			"type":   self.type.to_name(),
			"title":  self.title,
			"id":     self.topic_id,
			"link":   self.link,
			"posts":  self.posts,
			"views":  self.views,
			"is_wip": self.wip,
			"created_at": self.created_at.isoformat(),
		}

	def check_perm(self, user, perm):
		if not user.is_authenticated:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to ForumTopic.check_perm()")

		if perm == Permission.TOPIC_DISCARD:
			return self.author == user or user.rank.at_least(UserRank.EDITOR)

		else:
			raise Exception("Permission {} is not related to topics".format(perm.name))


if app.config.get("LOG_SQL"):
	import logging
	logging.basicConfig()
	logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
