# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


import datetime
import enum
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl

from flask import url_for
from sqlalchemy import and_, or_
from werkzeug.datastructures import MultiDict

from .base import db, Model
from .users import Permission

if TYPE_CHECKING:
	from app.querybuilder import QueryBuilder


class DashboardWidgetType(enum.Enum):
	SPOTLIGHT = "Spotlight"
	ROW = "Row"
	TAGS = "Tags"
	REVIEWS = "Reviews"
	CATEGORIES = "Categories"

	def to_name(self):
		return self.name.lower()

	def __str__(self):
		return self.name

	@classmethod
	def get(cls, name):
		try:
			return DashboardWidgetType[name.upper()]
		except KeyError:
			return None

	@classmethod
	def choices(cls):
		ret = [(choice, choice.value) for choice in cls]
		return ret

	@classmethod
	def coerce(cls, item):
		return item if isinstance(item, DashboardWidgetType) else DashboardWidgetType[item.upper()]


class Dashboard(Model):
	id         = db.Column(db.Integer, primary_key=True)
	title      = db.Column(db.String(100), nullable=False)
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	widgets    = db.relationship("DashboardWidget", back_populates="dashboard", lazy="dynamic",
			order_by="DashboardWidget.order", cascade="all, delete, delete-orphan")

	def check_perm(self, user, perm):
		if isinstance(perm, str):
			perm = Permission[perm]
		elif not isinstance(perm, Permission):
			raise Exception("Unknown permission given to Dashboard.check_perm()")

		if user is None or not user.is_authenticated:
			return False

		if perm == Permission.EDIT_DASHBOARD:
			return Permission.EDIT_DASHBOARD.check(user)

		else:
			raise Exception("Permission {} is not related to dashboards".format(perm.name))

	def as_dict(self):
		return {
			"id": self.id,
			"title": self.title,
			"widgets": [widget.as_dict() for widget in self.widgets],
		}


class DashboardWidget(Model):
	id = db.Column(db.Integer, primary_key=True)

	dashboard_id = db.Column(db.Integer, db.ForeignKey("dashboard.id"), nullable=False)
	dashboard = db.relationship("Dashboard", back_populates="widgets", foreign_keys=[dashboard_id])

	# Stored as a string rather than a native Postgres enum, so adding a widget type doesn't need a migration.
	# Renaming or removing a member does, as rows with the old name would fail to load.
	type = db.Column(db.Enum(DashboardWidgetType, native_enum=False, length=32), nullable=False,
			default=DashboardWidgetType.ROW)

	title = db.Column(db.String(100), nullable=True)
	order = db.Column(db.Integer, nullable=False)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	# Package list query, in the same format as /packages/'s URL query string, e.g. "type=game&sort=score".
	# Not called `query`, as that would shadow Model.query.
	query_string = db.Column(db.String(512), nullable=True)
	# None uses the widget type's default_limit. No column default, as SQLAlchemy would apply it in place of None.
	limit = db.Column(db.Integer, nullable=True)

	# Custom slides, for widget types with Widget.has_slides
	slides = db.relationship("DashboardWidgetSlide", back_populates="widget", lazy="dynamic",
			order_by="DashboardWidgetSlide.order", cascade="all, delete, delete-orphan", passive_deletes=True)

	def as_dict(self):
		return {
			"id": self.id,
			"type": self.type.to_name(),
			"title": self.title,
			"query_string": self.query_string,
			"limit": self.limit,
		}

	def get_query_builder(self) -> "QueryBuilder":
		# Imported here, as app.querybuilder imports app.models
		from app.querybuilder import QueryBuilder

		args = MultiDict(parse_qsl(self.query_string or "", keep_blank_values=True))
		return QueryBuilder(args, emit_http_errors=False)

	def get_see_more_url(self):
		return url_for("packages.list_all") + "?" + (self.query_string or "")


class DashboardWidgetSlide(Model):
	"""
	A custom slide in a carousel widget, such as one promoting a game jam.
	Shown before the widget's packages, between starts_at and ends_at (UTC). Either can be None for no limit.
	"""

	id = db.Column(db.Integer, primary_key=True)

	widget_id = db.Column(db.Integer, db.ForeignKey("dashboard_widget.id", ondelete="CASCADE"), nullable=False)
	widget = db.relationship("DashboardWidget", back_populates="slides", foreign_keys=[widget_id])

	order = db.Column(db.Integer, nullable=False)

	title = db.Column(db.String(100), nullable=False)
	description = db.Column(db.String(300), nullable=True)
	# Shown where a package's type would be, e.g. "Competition"
	label = db.Column(db.String(50), nullable=True)
	# An http(s) URL or a path on this site
	url = db.Column(db.String(512), nullable=False)
	# From app.uploads.upload_file
	image_path = db.Column(db.String(200), nullable=False)

	starts_at = db.Column(db.DateTime, nullable=True)
	ends_at = db.Column(db.DateTime, nullable=True)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	def get_image_url(self, level: int = 4) -> str:
		from app.uploads import get_thumbnail_url
		return get_thumbnail_url(self.image_path, level, "webp")

	def is_active(self, now: datetime.datetime) -> bool:
		return (self.starts_at is None or self.starts_at <= now) and (self.ends_at is None or now < self.ends_at)

	@classmethod
	def active_filter(cls, now: datetime.datetime):
		"""SQL equivalent of is_active"""
		return and_(
			or_(cls.starts_at.is_(None), cls.starts_at <= now),
			or_(cls.ends_at.is_(None), cls.ends_at > now))

