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


import datetime
import enum
import os

import typing
from flask import url_for
from flask_babel import lazy_gettext, get_locale, gettext, pgettext
from flask_sqlalchemy.query import Query
from sqlalchemy import or_, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy_searchable import SearchQueryMixin
from sqlalchemy_utils.types import TSVectorType

from app import app
from . import db
from .users import Permission, UserRank, User


class PackageQuery(Query, SearchQueryMixin):
	pass


class License(db.Model):
	id      = db.Column(db.Integer, primary_key=True)
	name    = db.Column(db.String(50), nullable=False, unique=True)
	is_foss = db.Column(db.Boolean,    nullable=False, default=True)
	url     = db.Column(db.String(128), nullable=True, default=None)

	def __init__(self, v: str, is_foss: bool = True, url: str = None):
		self.name = v
		self.is_foss = is_foss
		self.url = url

	def __str__(self):
		return self.name


class PackageType(enum.Enum):
	MOD  = "Mod"
	GAME = "Game"
	TXP  = "Texture Pack"

	def to_name(self):
		return self.name.lower()

	def __str__(self):
		return self.name

	@property
	def text(self):
		if self == PackageType.MOD:
			return lazy_gettext("Mod")
		elif self == PackageType.GAME:
			return lazy_gettext("Game")
		elif self == PackageType.TXP:
			return lazy_gettext("Texture Pack")

	@property
	def plural(self):
		if self == PackageType.MOD:
			return lazy_gettext("Mods")
		elif self == PackageType.GAME:
			return lazy_gettext("Games")
		elif self == PackageType.TXP:
			return lazy_gettext("Texture Packs")

	def get_top_ordinal(self, place: int):
		if place == 1:
			if self == PackageType.MOD:
				return lazy_gettext("Top mod")
			elif self == PackageType.GAME:
				return lazy_gettext("Top game")
			elif self == PackageType.TXP:
				return lazy_gettext("Top texture pack")
		else:
			if self == PackageType.MOD:
				return lazy_gettext("Top %(place)d mod", place=place)
			elif self == PackageType.GAME:
				return lazy_gettext("Top %(place)d game", place=place)
			elif self == PackageType.TXP:
				return lazy_gettext("Top %(place)d texture pack", place=place)

	def get_top_ordinal_description(self, display_name: str, place: int):
		if self == PackageType.MOD:
			return lazy_gettext(u"%(display_name)s has a mod placed at #%(place)d.",
					display_name=display_name,  place=place)
		elif self == PackageType.GAME:
			return lazy_gettext(u"%(display_name)s has a game placed at #%(place)d.",
					display_name=display_name,  place=place)
		elif self == PackageType.TXP:
			return lazy_gettext(u"%(display_name)s has a texture pack placed at #%(place)d.",
					display_name=display_name,  place=place)

	@property
	def do_you_recommend(self):
		if self == PackageType.MOD:
			return lazy_gettext(u"Do you recommend this mod?")
		elif self == PackageType.GAME:
			return lazy_gettext(u"Do you recommend this game?")
		elif self == PackageType.TXP:
			return lazy_gettext(u"Do you recommend this texture pack?")

	@classmethod
	def get(cls, name):
		try:
			return PackageType[name.upper()]
		except KeyError:
			return None

	@classmethod
	def choices(cls):
		return [(choice.name.lower(), choice.text) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == PackageType else PackageType[item.upper()]


class PackageDevState(enum.Enum):
	WIP = "Work in Progress"
	BETA = "Beta"
	ACTIVELY_DEVELOPED = "Actively Developed"
	MAINTENANCE_ONLY = "Maintenance Only"
	AS_IS = "As-Is"
	DEPRECATED = "Deprecated"
	LOOKING_FOR_MAINTAINER = "Looking for Maintainer"

	def to_name(self):
		return self.name.lower()

	def __str__(self):
		return self.name

	@property
	def title(self):
		if self == PackageDevState.WIP:
			# NOTE: Package maintenance state
			return lazy_gettext("Looking for Maintainer")
		elif self == PackageDevState.BETA:
			# NOTE: Package maintenance state
			return lazy_gettext("Beta")
		elif self == PackageDevState.ACTIVELY_DEVELOPED:
			# NOTE: Package maintenance state
			return lazy_gettext("Actively Developed")
		elif self == PackageDevState.MAINTENANCE_ONLY:
			# NOTE: Package maintenance state
			return lazy_gettext("Maintenance Only")
		elif self == PackageDevState.AS_IS:
			# NOTE: Package maintenance state
			return lazy_gettext("As-is")
		elif self == PackageDevState.DEPRECATED:
			# NOTE: Package maintenance state
			return lazy_gettext("Deprecated")
		elif self == PackageDevState.LOOKING_FOR_MAINTAINER:
			# NOTE: Package maintenance state
			return lazy_gettext("Looking for Maintainer")

	def get_desc(self):
		if self == PackageDevState.WIP:
			return lazy_gettext("Under active development, and may break worlds/things without warning")
		elif self == PackageDevState.BETA:
			return lazy_gettext("Fully playable, but with some breakages/changes expected")
		elif self == PackageDevState.MAINTENANCE_ONLY:
			return lazy_gettext("Finished, with bug fixes being made as needed")
		elif self == PackageDevState.AS_IS:
			return lazy_gettext("Finished, the maintainer doesn't intend to continue working on it or provide support")
		elif self == PackageDevState.DEPRECATED:
			return lazy_gettext("The maintainer doesn't recommend this package. See the description for more info")
		else:
			return None

	@classmethod
	def get(cls, name):
		try:
			return PackageDevState[name.upper()]
		except KeyError:
			return None

	@classmethod
	def choices(cls, with_none):
		def build_label(choice):
			desc = choice.get_desc()
			if desc is None:
				return choice.value
			else:
				return f"{choice.value}: {desc}"

		ret = [(choice, build_label(choice)) for choice in cls]

		if with_none:
			ret.insert(0, (None, ""))

		return ret

	@classmethod
	def coerce(cls, item):
		if item is None or (isinstance(item, str) and item.upper() == "NONE"):
			return None
		return item if type(item) == PackageDevState else PackageDevState[item.upper()]


class PackageState(enum.Enum):
	WIP = "Draft"
	CHANGES_NEEDED  = "Changes Needed"
	READY_FOR_REVIEW = "Ready for Review"
	APPROVED = "Approved"
	DELETED = "Deleted"

	def to_name(self):
		return self.name.lower()

	def verb(self):
		if self == self.READY_FOR_REVIEW:
			return lazy_gettext("Submit for Approval")
		elif self == self.APPROVED:
			return lazy_gettext("Approve")
		elif self == self.DELETED:
			return lazy_gettext("Delete")
		else:
			return self.value

	def __str__(self):
		return self.name

	@property
	def color(self):
		if self == self.WIP:
			return "warning"
		elif self == self.CHANGES_NEEDED:
			return "danger"
		elif self == self.READY_FOR_REVIEW:
			return "success"
		elif self == self.APPROVED:
			return "info"
		else:
			return "danger"

	@classmethod
	def get(cls, name):
		try:
			return PackageState[name.upper()]
		except KeyError:
			return None

	@classmethod
	def choices(cls):
		return [(choice, choice.value) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == PackageState else PackageState[item.upper()]


PackageProvides = db.Table("provides",
	db.Column("package_id",    db.Integer, db.ForeignKey("package.id"), primary_key=True),
	db.Column("metapackage_id", db.Integer, db.ForeignKey("meta_package.id"), primary_key=True)
)


Tags = db.Table("tags",
	db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
	db.Column("package_id", db.Integer, db.ForeignKey("package.id"), primary_key=True)
)


ContentWarnings = db.Table("content_warnings",
	db.Column("content_warning_id", db.Integer, db.ForeignKey("content_warning.id"), primary_key=True),
	db.Column("package_id", db.Integer, db.ForeignKey("package.id"), primary_key=True)
)


maintainers = db.Table("maintainers",
	db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
	db.Column("package_id", db.Integer, db.ForeignKey("package.id"), primary_key=True)
)


class Dependency(db.Model):
	id              = db.Column(db.Integer, primary_key=True)

	depender_id     = db.Column(db.Integer, db.ForeignKey("package.id"),     nullable=True)
	depender        = db.relationship("Package", foreign_keys=[depender_id])

	package_id      = db.Column(db.Integer, db.ForeignKey("package.id"),     nullable=True)
	package         = db.relationship("Package", foreign_keys=[package_id])

	meta_package_id = db.Column(db.Integer, db.ForeignKey("meta_package.id"), nullable=True)
	meta_package = db.relationship("MetaPackage", foreign_keys=[meta_package_id])

	optional        = db.Column(db.Boolean, nullable=False, default=False)

	__table_args__  = (db.UniqueConstraint("depender_id", "package_id", "meta_package_id", name="_dependency_uc"), )

	def __init__(self, depender=None, package=None, meta=None, optional=False):
		if depender is None:
			return

		self.depender = depender
		self.optional = optional

		packageProvided = package is not None
		metaProvided = meta is not None

		if packageProvided and not metaProvided:
			self.package = package
		elif metaProvided and not packageProvided:
			self.meta_package = meta
		else:
			raise Exception("Either meta or package must be given, but not both!")

	def get_name(self):
		if self.meta_package:
			return self.meta_package.name
		elif self.package:
			return self.package.name
		else:
			assert False

	def __str__(self):
		if self.package is not None:
			return self.package.author.username + "/" + self.package.name
		elif self.meta_package is not None:
			return self.meta_package.name
		else:
			raise Exception("Meta and package are both none!")

	@staticmethod
	def SpecToList(depender, spec, cache):
		retval = []
		arr = spec.split(",")

		import re
		pattern1 = re.compile("^([a-z0-9_]+)$")
		pattern2 = re.compile("^([A-Za-z0-9_]+)/([a-z0-9_]+)$")

		for x in arr:
			x = x.strip()
			if x == "":
				continue

			if pattern1.match(x):
				meta = MetaPackage.GetOrCreate(x, cache)
				retval.append(Dependency(depender, meta=meta))
			else:
				m = pattern2.match(x)
				username = m.group(1)
				name     = m.group(2)
				user = User.query.filter_by(username=username).first()
				if user is None:
					raise Exception("Unable to find user " + username)

				package = Package.query.filter_by(author=user, name=name).first()
				if package is None:
					raise Exception("Unable to find package " + name + " by " + username)

				retval.append(Dependency(depender, package=package))

		return retval


class PackageGameSupport(db.Model):
	id = db.Column(db.Integer, primary_key=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
	package = db.relationship("Package", foreign_keys=[package_id])

	game_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
	game = db.relationship("Package", foreign_keys=[game_id])

	supports = db.Column(db.Boolean, nullable=False, default=True)
	confidence = db.Column(db.Integer, nullable=False, default=1)

	__table_args__ = (db.UniqueConstraint("game_id", "package_id", name="_package_game_support_uc"),)


class Package(db.Model):
	query_class  = PackageQuery

	id           = db.Column(db.Integer, primary_key=True)

	# Basic details
	author_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author       = db.relationship("User", back_populates="packages", foreign_keys=[author_id])

	name         = db.Column(db.Unicode(100), nullable=False)
	title        = db.Column(db.Unicode(100), nullable=False)
	short_desc   = db.Column(db.Unicode(200), nullable=False)
	desc         = db.Column(db.UnicodeText, nullable=True)
	type         = db.Column(db.Enum(PackageType), nullable=False)
	created_at   = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
	approved_at  = db.Column(db.DateTime, nullable=True, default=None)

	name_valid = db.CheckConstraint("name ~* '^[a-z0-9_]+$' AND name != '_game'")

	search_vector = db.Column(TSVectorType("name", "title", "short_desc", "desc",
			weights={ "name": "A", "title": "B", "short_desc": "C" }))

	__table_args__ = (db.UniqueConstraint("author_id", "name", name="_package_uc"),)

	license_id   = db.Column(db.Integer, db.ForeignKey("license.id"), nullable=False, default=1)
	license      = db.relationship("License", foreign_keys=[license_id])
	media_license_id = db.Column(db.Integer, db.ForeignKey("license.id"), nullable=False, default=1)
	media_license    = db.relationship("License", foreign_keys=[media_license_id])

	ck_license_txp = db.CheckConstraint("type != 'TXP' OR license_id = media_license_id")

	state     = db.Column(db.Enum(PackageState), nullable=False, default=PackageState.WIP)
	dev_state = db.Column(db.Enum(PackageDevState), nullable=True, default=None)

	@property
	def approved(self):
		return self.state == PackageState.APPROVED

	score        = db.Column(db.Float, nullable=False, default=0)
	score_downloads = db.Column(db.Float, nullable=False, default=0)
	downloads     = db.Column(db.Integer, nullable=False, default=0)

	review_thread_id = db.Column(db.Integer, db.ForeignKey("thread.id"), nullable=True, default=None)
	review_thread    = db.relationship("Thread", uselist=False, foreign_keys=[review_thread_id],
			back_populates="is_review_thread", post_update=True)

	# Supports all games by default, may have unsupported games
	supports_all_games = db.Column(db.Boolean, nullable=False, default=False)

	# Downloads
	repo         = db.Column(db.String(200), nullable=True)
	website      = db.Column(db.String(200), nullable=True)
	issueTracker = db.Column(db.String(200), nullable=True)
	forums       = db.Column(db.Integer,     nullable=True)
	video_url    = db.Column(db.String(200), nullable=True, default=None)
	donate_url   = db.Column(db.String(200), nullable=True, default=None)
	translation_url = db.Column(db.String(200), nullable=True)

	@property
	def donate_url_actual(self):
		return self.donate_url or self.author.donate_url

	@property
	def forums_url(self) -> typing.Optional[str]:
		if self.forums is None:
			return None

		return "https://forum.luanti.org/viewtopic.php?t=" + str(self.forums)

	enable_game_support_detection = db.Column(db.Boolean, nullable=False, default=True)

	translations = db.relationship("PackageTranslation", back_populates="package",
			lazy="dynamic", order_by=db.asc("package_translation_language_id"),
			cascade="all, delete, delete-orphan")

	provides = db.relationship("MetaPackage", secondary=PackageProvides, order_by=db.asc("name"), back_populates="packages")

	dependencies = db.relationship("Dependency", back_populates="depender", lazy="dynamic", foreign_keys=[Dependency.depender_id])

	supported_games = db.relationship("PackageGameSupport", back_populates="package", lazy="dynamic",
			foreign_keys=[PackageGameSupport.package_id], cascade="all, delete, delete-orphan")

	game_supported_mods = db.relationship("PackageGameSupport", back_populates="game", lazy="dynamic",
			foreign_keys=[PackageGameSupport.game_id], cascade="all, delete, delete-orphan")

	tags = db.relationship("Tag", secondary=Tags, back_populates="packages")

	content_warnings = db.relationship("ContentWarning", secondary=ContentWarnings, back_populates="packages")

	releases = db.relationship("PackageRelease", back_populates="package",
			lazy="dynamic", order_by=db.desc("package_release_created_at"), cascade="all, delete, delete-orphan")

	screenshots = db.relationship("PackageScreenshot", back_populates="package", foreign_keys="PackageScreenshot.package_id",
			lazy="dynamic", order_by=db.asc("package_screenshot_order"), cascade="all, delete, delete-orphan")

	main_screenshot = db.relationship("PackageScreenshot", uselist=False, foreign_keys="PackageScreenshot.package_id",
			lazy=True, order_by=db.asc("package_screenshot_order"), viewonly=True,
			primaryjoin="and_(Package.id==PackageScreenshot.package_id, PackageScreenshot.approved)")

	cover_image_id = db.Column(db.Integer, db.ForeignKey("package_screenshot.id"), nullable=True, default=None)
	cover_image = db.relationship("PackageScreenshot", uselist=False, foreign_keys=[cover_image_id], post_update=True)

	maintainers = db.relationship("User", secondary=maintainers)

	threads = db.relationship("Thread", back_populates="package", order_by=db.desc("thread_created_at"),
			foreign_keys="Thread.package_id", cascade="all, delete, delete-orphan", lazy="dynamic")

	reviews = db.relationship("PackageReview", back_populates="package", lazy="dynamic",
			order_by=[db.desc("package_review_score"), db.desc("package_review_created_at")],
			cascade="all, delete, delete-orphan")

	audit_log_entries = db.relationship("AuditLogEntry", foreign_keys="AuditLogEntry.package_id",
			lazy="dynamic", back_populates="package", order_by=db.desc("audit_log_entry_created_at"))

	notifications = db.relationship("Notification", foreign_keys="Notification.package_id",
			back_populates="package", cascade="all, delete, delete-orphan")

	tokens = db.relationship("APIToken", foreign_keys="APIToken.package_id", back_populates="package",
			cascade="all, delete")

	update_config = db.relationship("PackageUpdateConfig", uselist=False, back_populates="package",
			cascade="all, delete, delete-orphan")

	aliases = db.relationship("PackageAlias",  foreign_keys="PackageAlias.package_id",
			back_populates="package", cascade="all, delete, delete-orphan")

	daily_stats = db.relationship("PackageDailyStats", foreign_keys="PackageDailyStats.package_id",
			back_populates="package", cascade="all, delete, delete-orphan", lazy="dynamic")

	def __init__(self, package=None):
		if package is None:
			return

		self.author_id = package.author_id
		self.created_at = package.created_at
		self.state = package.state

		self.maintainers.append(self.author)

	@classmethod
	def get_by_key(cls, key):
		parts = key.split("/")
		if len(parts) != 2:
			return None

		name = parts[1]
		if name.endswith("_game"):
			name = name[:-5]

		return Package.query.filter(or_(Package.name == name, Package.name == name + "_game"),
			Package.author.has(username=parts[0])).first()

	def get_id(self):
		return "{}/{}".format(self.author.username, self.name)

	@property
	def normalised_name(self):
		name = self.name
		if name.endswith("_game"):
			name = name[:-5]
		return name

	def get_translated(self, lang=None, load_desc=True):
		if lang is None:
			locale = get_locale()
			if locale:
				lang = locale.language
			else:
				lang = "en"

		translation: typing.Optional[PackageTranslation] = None
		if lang != "en":
			translation = self.translations.filter_by(language_id=lang).first()

		if translation is None:
			return {
				"title": self.title,
				"short_desc": self.short_desc,
				"desc": self.desc if load_desc else None,
			}

		return {
			"title": translation.title or self.title,
			"short_desc": translation.short_desc or self.short_desc,
			"desc": (translation.desc or self.desc) if load_desc else None,
		}

	def get_sorted_dependencies(self, is_hard=None):
		query = self.dependencies
		if is_hard is not None:
			query = query.filter_by(optional=not is_hard)

		deps = query.all()
		deps.sort(key=lambda x: x.get_name())
		return deps

	def get_sorted_hard_dependencies(self):
		return self.get_sorted_dependencies(True)

	def get_sorted_optional_dependencies(self):
		return self.get_sorted_dependencies(False)

	def get_sorted_game_support(self) -> list[PackageGameSupport]:
		query = self.supported_games.filter(PackageGameSupport.game.has(state=PackageState.APPROVED))

		supported = query.all()
		supported.sort(key=lambda x: -(x.game.score + 100000*x.confidence))
		return supported

	def get_sorted_game_support_pair(self) -> list[list[PackageGameSupport]]:
		supported = self.get_sorted_game_support()
		return [
			[x for x in supported if x.supports],
			[x for x in supported if not x.supports],
		]

	def has_game_support_confirmed(self):
		return self.supports_all_games or \
				self.supported_games.filter(PackageGameSupport.confidence > 1).count() > 0

	def as_key_dict(self):
		return {
			"name": self.name,
			"author": self.author.username,
			"type": self.type.to_name(),
		}

	def as_short_dict(self, base_url, version=None, release_id=None, no_load=False, lang="en", include_vcs=False):
		tnurl = self.get_thumb_url(1, format="png")

		if release_id is None and no_load == False:
			release = self.get_download_release(version=version)
			release_id = release and release.id

		meta = self.get_translated(lang, load_desc=False)
		short_desc = meta["short_desc"]
		if self.dev_state == PackageDevState.WIP:
			short_desc = gettext("Work in Progress") + ". " + self.short_desc

		ret = {
			"name": self.name,
			"title": meta["title"],
			"author": self.author.username,
			"short_description": short_desc,
			"type": self.type.to_name(),
			"release": release_id,
			"thumbnail": (base_url + tnurl) if tnurl is not None else None,
			"aliases": [alias.as_dict() for alias in self.aliases],
		}

		if not ret["aliases"]:
			del ret["aliases"]

		if include_vcs:
			ret["repo"] = self.repo

		return ret

	def as_dict(self, base_url, version=None, lang="en", screenshots_dict=False):
		tnurl = self.get_thumb_url(1, format="png")
		release = self.get_download_release(version=version)
		meta = self.get_translated(lang)

		if screenshots_dict:
			screenshots = [ss.as_short_dict(base_url) for ss in self.screenshots]
		else:
			screenshots = [base_url + ss.url for ss in self.screenshots]

		return {
			"author": self.author.username,
			"maintainers": [x.username for x in self.maintainers],

			"state": self.state.name,
			"dev_state": self.dev_state.name if self.dev_state else None,

			"name": self.name,
			"title": meta["title"],
			"short_description": meta["short_desc"],
			"long_description": meta["desc"],
			"type": self.type.to_name(),
			"created_at": self.created_at.isoformat(),

			"license": self.license.name,
			"media_license": self.media_license.name,

			"repo": self.repo,
			"website": self.website,
			"issue_tracker": self.issueTracker,
			"forums": self.forums,
			"forum_url": self.forums_url,
			"video_url": self.video_url,
			"video_thumbnail_url": self.get_video_thumbnail_url(True),
			"donate_url": self.donate_url_actual,
			"translation_url": self.translation_url,

			"tags": sorted([x.name for x in self.tags]),
			"content_warnings": sorted([x.name for x in self.content_warnings]),

			"provides": sorted([x.name for x in self.provides]),
			"thumbnail": (base_url + tnurl) if tnurl is not None else None,
			"screenshots": screenshots,

			"url": base_url + self.get_url("packages.download"),
			"release": release and release.id,

			"score": round(self.score * 10) / 10,
			"downloads": self.downloads,

			"game_support": [
				{
					"supports": support.supports,
					"confidence": support.confidence,
					"game": support.game.as_short_dict(base_url, version)
				} for support in self.supported_games.all()
			]
		}

	def get_thumb_or_placeholder(self, level=2, format="webp"):
		return self.get_thumb_url(level, False, format) or "/static/placeholder.png"

	def get_thumb_url(self, level=2, abs=False, format="webp"):
		screenshot = self.main_screenshot
		url = screenshot.get_thumb_url(level, format) if screenshot is not None else None
		if abs:
			from app.utils import abs_url
			return abs_url(url)
		else:
			return url

	def get_cover_image_url(self, format="webp"):
		screenshot = self.cover_image or self.main_screenshot
		return screenshot and screenshot.get_thumb_url(4, format)

	def get_url(self, endpoint, absolute=False, **kwargs):
		if absolute:
			from app.utils import abs_url_for
			return abs_url_for(endpoint, author=self.author.username, name=self.name, **kwargs)
		else:
			return url_for(endpoint, author=self.author.username, name=self.name, **kwargs)

	def get_shield_url(self, type):
		from app.utils import abs_url_for
		return abs_url_for("packages.shield",
				author=self.author.username, name=self.name, type=type)

	def make_shield(self, type):
		return "[![ContentDB]({})]({})" \
			.format(self.get_shield_url(type), self.get_url("packages.view", True))

	def get_video_thumbnail_url(self, absolute: bool = False):
		from app.utils.url import get_youtube_id

		if self.video_url is None:
			return None

		id_ = get_youtube_id(self.video_url)
		if id_ is None:
			return None

		if absolute:
			from app.utils import abs_url_for
			return abs_url_for("thumbnails.youtube", id_=id_)
		else:
			return url_for("thumbnails.youtube", id_=id_)

	def get_set_state_url(self, state):
		if type(state) == str:
			state = PackageState[state]
		elif type(state) != PackageState:
			raise Exception("Unknown state given to Package.get_set_state_url()")

		return url_for("packages.move_to_state",
				author=self.author.username, name=self.name, state=state.name.lower())

	def get_download_release(self, version=None) -> typing.Optional["PackageRelease"]:
		for rel in self.releases:
			if rel.approved and (version is None or
					((rel.min_rel is None or rel.min_rel_id <= version.id) and
					(rel.max_rel is None or rel.max_rel_id >= version.id))):
				return rel

		return None

	def check_perm(self, user, perm):
		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to Package.check_perm()")

		if perm == Permission.VIEW_PACKAGE:
			return self.state == PackageState.APPROVED or self.check_perm(user, Permission.EDIT_PACKAGE)

		if not user.is_authenticated:
			return False

		is_owner = user == self.author
		is_maintainer = is_owner or user.rank.at_least(UserRank.EDITOR) or user in self.maintainers
		is_approver = user.rank.at_least(UserRank.APPROVER)

		if perm == Permission.CREATE_THREAD:
			return user.rank.at_least(UserRank.NEW_MEMBER)

		# Members can edit their own packages, and editors can edit any packages
		elif perm == Permission.MAKE_RELEASE or perm == Permission.ADD_SCREENSHOTS:
			return is_maintainer

		elif perm == Permission.EDIT_PACKAGE:
			return is_maintainer and user.rank.at_least(UserRank.NEW_MEMBER)

		elif perm == Permission.APPROVE_RELEASE:
			return (is_maintainer or is_approver) and user.rank.at_least(UserRank.MEMBER if self.approved else UserRank.NEW_MEMBER)

		# Anyone can change the package name when not approved
		elif perm == Permission.CHANGE_NAME:
			return not self.approved

		# Editors can change authors and approve new packages
		elif perm == Permission.APPROVE_NEW or perm == Permission.CHANGE_AUTHOR:
			return is_approver

		elif perm == Permission.APPROVE_SCREENSHOT:
			return (is_maintainer or is_approver) and \
				user.rank.at_least(UserRank.TRUSTED_MEMBER if self.approved else UserRank.NEW_MEMBER)

		elif perm == Permission.EDIT_MAINTAINERS or perm == Permission.DELETE_PACKAGE:
			return is_owner or user.rank.at_least(UserRank.EDITOR)

		elif perm == Permission.UNAPPROVE_PACKAGE:
			return is_owner or user.rank.at_least(UserRank.APPROVER)

		elif perm == Permission.CHANGE_RELEASE_URL:
			return user.rank.at_least(UserRank.MODERATOR)

		else:
			raise Exception("Permission {} is not related to packages".format(perm.name))

	def get_missing_hard_dependencies_query(self):
		return MetaPackage.query \
			.filter(~ MetaPackage.packages.any(state=PackageState.APPROVED)) \
			.filter(MetaPackage.dependencies.any(optional=False, depender=self)) \
			.order_by(db.asc(MetaPackage.name))

	def get_missing_hard_dependencies(self):
		return [mp.name for mp in self.get_missing_hard_dependencies_query().all()]

	def get_next_states(self, user):
		from app.logic.package_approval import can_move_to_state

		states = []

		for state in PackageState:
			if can_move_to_state(self, user, state):
				states.append(state)

		return states

	def as_score_dict(self):
		reviews = self.get_review_summary()
		return {
			"author": self.author.username,
			"name": self.name,
			"score": self.score,
			"score_downloads": self.score_downloads,
			"score_reviews": self.score - self.score_downloads,
			"downloads": self.downloads,
			"reviews": {
				"positive": reviews[0],
				"neutral": reviews[1],
				"negative": reviews[2],
			},
		}

	def recalculate_score(self):
		review_scores = [ 150 * r.as_weight() for r in self.reviews ]
		self.score = self.score_downloads + sum(review_scores)

	def get_conf_file_name(self):
		if self.type == PackageType.MOD:
			return "mod.conf"
		elif self.type == PackageType.TXP:
			return "texture_pack.conf"
		elif self.type == PackageType.GAME:
			return "game.conf"

	def get_review_summary(self):
		from app.models import PackageReview
		rows = (db.session.query(PackageReview.rating, func.count(PackageReview.id))
			.select_from(PackageReview)
			.where(PackageReview.package_id == self.id)
			.group_by(PackageReview.rating)
			.all())

		negative = 0
		neutral = 0
		positive = 0
		for rating, count in rows:
			if rating > 3:
				positive += count
			elif rating == 3:
				neutral += count
			else:
				negative += count

		return [positive, neutral, negative]


class Language(db.Model):
	id = db.Column(db.String(10), primary_key=True)
	title = db.Column(db.String(100), unique=True, nullable=False)

	packages = db.relationship("Package", secondary="package_translation", lazy="dynamic")

	@property
	def has_contentdb_translation(self):
		return self.id in app.config["LANGUAGES"].keys()

	def as_dict(self):
		return {
			"id": self.id,
			"title": self.title,
			"has_contentdb_translation": self.has_contentdb_translation,
		}


class PackageTranslation(db.Model):
	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), primary_key=True)
	package = db.relationship("Package", back_populates="translations", foreign_keys=[package_id])

	language_id = db.Column(db.String(10), db.ForeignKey("language.id"), primary_key=True)
	language = db.relationship("Language", foreign_keys=[language_id])

	title = db.Column(db.Unicode(100), nullable=True)
	short_desc = db.Column(db.Unicode(200), nullable=True)
	desc = db.Column(db.UnicodeText, nullable=True)


class MetaPackage(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), unique=True, nullable=False)
	dependencies = db.relationship("Dependency", back_populates="meta_package", lazy="dynamic")
	packages = db.relationship("Package", lazy="dynamic", back_populates="provides", secondary=PackageProvides)

	mp_name_valid = db.CheckConstraint("name ~* '^[a-z0-9_]+$'")

	def __init__(self, name=None):
		self.name = name

	def __str__(self):
		return self.name

	@staticmethod
	def ListToSpec(list):
		return ",".join([str(x) for x in list])

	@staticmethod
	def GetOrCreate(name, cache):
		mp = cache.get(name)
		if mp is None:
			mp = MetaPackage.query.filter_by(name=name).first()

		if mp is None:
			mp = MetaPackage(name)
			db.session.add(mp)

		cache[name] = mp
		return mp

	@staticmethod
	def SpecToList(spec, cache):
		retval = []
		arr = spec.split(",")

		import re
		pattern = re.compile("^([a-z0-9_]+)$")

		for x in arr:
			x = x.strip()
			if x == "":
				continue

			if not pattern.match(x):
				continue

			retval.append(MetaPackage.GetOrCreate(x, cache))

		return retval


class ContentWarning(db.Model):
	id              = db.Column(db.Integer, primary_key=True)
	name            = db.Column(db.String(100), unique=True, nullable=False)
	title           = db.Column(db.String(100), nullable=False)
	description     = db.Column(db.String(500), nullable=False)

	packages        = db.relationship("Package", back_populates="content_warnings", secondary=ContentWarnings)

	def __init__(self, title, description=""):
		self.title       = title
		self.description = description

		import re
		regex = re.compile("[^a-z_]")
		self.name = regex.sub("", self.title.lower().replace(" ", "_"))

	def get_translated(self):
		# Translations are automated on dynamic data using `extract_translations.py`
		return {
			"title": pgettext("tags", self.title),
			"description": pgettext("content_warnings", self.description),
		}

	def as_dict(self):
		description = self.description if self.description != "" else None
		return { "name": self.name, "title": self.title, "description": description }


class Tag(db.Model):
	id              = db.Column(db.Integer, primary_key=True)
	name            = db.Column(db.String(100), unique=True, nullable=False)
	title           = db.Column(db.String(100), nullable=False)
	description     = db.Column(db.String(500), nullable=True, default=None)
	backgroundColor = db.Column(db.String(6), nullable=False)
	textColor       = db.Column(db.String(6), nullable=False)
	views           = db.Column(db.Integer, nullable=False, default=0)

	packages        = db.relationship("Package", back_populates="tags", secondary=Tags)

	def __init__(self, title, backgroundColor="000000", textColor="ffffff"):
		self.title           = title
		self.backgroundColor = backgroundColor
		self.textColor       = textColor

		import re
		regex = re.compile("[^a-z_]")
		self.name = regex.sub("", self.title.lower().replace(" ", "_"))

	def get_translated(self):
		# Translations are automated on dynamic data using `extract_translations.py`
		return {
			"title": pgettext("tags", self.title),
			"description": pgettext("tags", self.description) if self.description else "",
		}

	def as_dict(self):
		description = self.description if self.description != "" else None
		return {
			"name": self.name,
			"title": self.title,
			"description": description,
			"views": self.views,
		}


class LuantiRelease(db.Model):
	id       = db.Column(db.Integer, primary_key=True)
	name     = db.Column(db.String(100), unique=True, nullable=False)
	protocol = db.Column(db.Integer, nullable=False, default=0)

	def __init__(self, name=None, protocol=0):
		self.name = name
		self.protocol = protocol

	@property
	def value(self):
		return self.name

	def get_actual(self):
		return None if self.name == "None" else self

	def as_dict(self):
		return {
			"name": self.name,
			"protocol_version": self.protocol,
			"is_dev": "-dev" in self.name,
		}

	@classmethod
	def get(cls, version: typing.Optional[str], protocol_num: typing.Optional[str]) -> typing.Optional["LuantiRelease"]:
		if version:
			parts = version.strip().split(".")
			if len(parts) >= 2:
				query = LuantiRelease.query.filter(func.replace(LuantiRelease.name, "-dev", "") == "{}.{}".format(parts[0], parts[1]))
				if protocol_num:
					query = query.filter_by(protocol=protocol_num)

				release = query.one_or_none()
				if release:
					return release

		if protocol_num:
			# Find the closest matching release
			return LuantiRelease.query.order_by(db.desc(LuantiRelease.protocol),
							db.desc(LuantiRelease.id)) \
						.filter(LuantiRelease.protocol <= protocol_num).first()

		return None

class ReleaseState(enum.Enum):
	PROCESSING = "Processing"
	APPROVED = "Approved"
	FAILED = "Failed"
	UNAPPROVED = "Waiting approval"
	ARCHIVED = "Archived"

	def to_name(self):
		return self.name.lower()

	@property
	def title(self):
		if self == self.PROCESSING:
			return lazy_gettext("Processing")
		elif self == self.APPROVED:
			return lazy_gettext("Approved")
		elif self == self.FAILED:
			return lazy_gettext("Failed")
		elif self == self.UNAPPROVED:
			return lazy_gettext("Waiting approval")
		elif self == self.ARCHIVED:
			return lazy_gettext("Archived")
		else:
			return self.value

	def __str__(self):
		return self.name

	@classmethod
	def get(cls, name):
		try:
			return ReleaseState[name.upper()]
		except KeyError:
			return None

	@classmethod
	def choices(cls):
		return [(choice, choice.value) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == ReleaseState else ReleaseState[item.upper()]


class PackageRelease(db.Model):
	id           = db.Column(db.Integer, primary_key=True)

	package_id   = db.Column(db.Integer, db.ForeignKey("package.id"))
	package      = db.relationship("Package", back_populates="releases", foreign_keys=[package_id])

	name         = db.Column(db.String(30), nullable=False)
	title        = db.Column(db.String(100), nullable=False)
	created_at  = db.Column(db.DateTime,    nullable=False)
	url          = db.Column(db.String(200), nullable=False, default="")
	state     = db.Column(db.Enum(ReleaseState), nullable=False, default=ReleaseState.PROCESSING)

	@property
	def approved(self):
		return self.state == ReleaseState.APPROVED

	task_id      = db.Column(db.String(37), nullable=True)
	commit_hash  = db.Column(db.String(41), nullable=True, default=None)
	downloads    = db.Column(db.Integer, nullable=False, default=0)
	release_notes = db.Column(db.UnicodeText, nullable=True, default=None)
	file_size_bytes = db.Column(db.Integer, nullable=False, default=0)

	@property
	def summary(self) -> str:
		if self.release_notes is None or \
				self.release_notes.startswith("-") or \
				self.release_notes.startswith("*"):
			return self.title

		return self.release_notes.split("\n")[0]

	min_rel_id = db.Column(db.Integer, db.ForeignKey("luanti_release.id"), nullable=True, server_default=None)
	min_rel    = db.relationship("LuantiRelease", foreign_keys=[min_rel_id])

	max_rel_id = db.Column(db.Integer, db.ForeignKey("luanti_release.id"), nullable=True, server_default=None)
	max_rel    = db.relationship("LuantiRelease", foreign_keys=[max_rel_id])

	# If the release is approved, then the task_id must be null and the url must be present
	CK_approval_valid = db.CheckConstraint("state != 'APPROVED' OR (task_id IS NULL AND url != '' AND url IS NOT NULL)")

	@property
	def file_path(self):
		return self.url.replace("/uploads/", app.config["UPLOAD_DIR"])

	def calculate_file_size_bytes(self):
		path = self.file_path
		if not os.path.isfile(path):
			self.file_size_bytes = 0
			return

		file_stats = os.stat(path)
		self.file_size_bytes = file_stats.st_size

	@property
	def file_size(self):
		size = self.file_size_bytes / 1024
		if size > 1024:
			return f"{round(size / 1024, 1)} MB"
		else:
			return f"{round(size)} KB"

	def as_dict(self):
		return {
			"id": self.id,
			"name": self.name,
			"title": self.title,
			"release_notes": self.release_notes,
			"url": self.url if self.url != "" else None,
			"release_date": self.created_at.isoformat(),
			"commit": self.commit_hash,
			"downloads": self.downloads,
			"min_minetest_version": self.min_rel and self.min_rel.as_dict(),
			"max_minetest_version": self.max_rel and self.max_rel.as_dict(),
			"size": self.file_size_bytes,
		}

	def as_long_dict(self):
		return {
			"id": self.id,
			"title": self.title,
			"url": self.url if self.url != "" else None,
			"release_date": self.created_at.isoformat(),
			"commit": self.commit_hash,
			"downloads": self.downloads,
			"min_minetest_version": self.min_rel and self.min_rel.as_dict(),
			"max_minetest_version": self.max_rel and self.max_rel.as_dict(),
			"package": self.package.as_key_dict(),
			"size": self.file_size_bytes,
		}

	def get_edit_url(self):
		return url_for("packages.edit_release",
				author=self.package.author.username,
				name=self.package.name,
				id=self.id)

	def get_delete_url(self):
		return url_for("packages.delete_release",
				author=self.package.author.username,
				name=self.package.name,
				id=self.id)

	def get_download_url(self):
		return url_for("packages.download_release",
				author=self.package.author.username,
				name=self.package.name,
				id=self.id)

	def __init__(self):
		self.created_at = datetime.datetime.now()

	def get_download_filename(self):
		return f"{self.package.name}_{self.id}.zip"

	def approve(self, user):
		if (not self.check_perm(user, Permission.APPROVE_RELEASE) or
				self.state == ReleaseState.PROCESSING or
				self.state == ReleaseState.FAILED):
			return False

		if self.approved:
			return True

		assert self.task_id is None and self.url is not None and self.url != ""

		self.state = ReleaseState.APPROVED

		if self.package.update_config:
			self.package.update_config.outdated_at = None
			self.package.update_config.last_commit = self.commit_hash

		return True

	def check_perm(self, user, perm):
		if not hasattr(user, "rank") or user.is_banned:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to PackageRelease.check_perm()")

		is_maintainer = user == self.package.author or user in self.package.maintainers

		if perm == Permission.DELETE_RELEASE:
			if user.rank.at_least(UserRank.ADMIN):
				return True

			if not (is_maintainer or user.rank.at_least(UserRank.EDITOR)):
				return False

			if not self.package.approved or self.task_id is not None:
				return True

			count = self.package.releases \
					.filter(PackageRelease.id > self.id) \
					.count()

			return count > 0
		elif perm == Permission.APPROVE_RELEASE:
			return is_maintainer or user.rank.at_least(UserRank.APPROVER)
		else:
			raise Exception("Permission {} is not related to releases".format(perm.name))


class PackageScreenshot(db.Model):
	HARD_MIN_SIZE = (920, 517)
	SOFT_MIN_SIZE = (1280, 720)

	id         = db.Column(db.Integer, primary_key=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
	package    = db.relationship("Package", back_populates="screenshots", foreign_keys=[package_id])

	order      = db.Column(db.Integer, nullable=False, default=0)
	title      = db.Column(db.String(100), nullable=False)
	url        = db.Column(db.String(100), nullable=False)
	approved   = db.Column(db.Boolean, nullable=False, default=False)
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	width      = db.Column(db.Integer, nullable=False)
	height     = db.Column(db.Integer, nullable=False)

	file_size_bytes = db.Column(db.Integer, nullable=False, default=0)

	def is_very_small(self):
		return self.width < 720 or self.height < 405

	def is_too_small(self):
		return self.width < PackageScreenshot.HARD_MIN_SIZE[0] or self.height < PackageScreenshot.HARD_MIN_SIZE[1]

	def is_low_res(self):
		return self.width < PackageScreenshot.SOFT_MIN_SIZE[0] or self.height < PackageScreenshot.SOFT_MIN_SIZE[1]

	@property
	def file_path(self):
		return self.url.replace("/uploads/", app.config["UPLOAD_DIR"])

	def calculate_file_size_bytes(self):
		path = self.file_path
		if not os.path.isfile(path):
			self.file_size_bytes = 0
			return

		file_stats = os.stat(path)
		self.file_size_bytes = file_stats.st_size

	@property
	def file_size(self):
		size = self.file_size_bytes / 1024
		if size > 1024:
			return f"{round(size / 1024, 1)} MB"
		else:
			return f"{round(size)} KB"

	def get_edit_url(self):
		return url_for("packages.edit_screenshot",
				author=self.package.author.username,
				name=self.package.name,
				id=self.id)

	def get_delete_url(self):
		return url_for("packages.delete_screenshot",
				author=self.package.author.username,
				name=self.package.name,
				id=self.id)

	def get_thumb_url(self, level=2, format="webp"):
		url = self.url.replace("/uploads/", "/thumbnails/{:d}/".format(level))
		if format is not None:
			start = url[:url.rfind(".")]
			url = f"{start}.{format}"
		return url

	def as_dict(self, base_url=""):
		return {
			"id": self.id,
			"order": self.order,
			"title": self.title,
			"url": base_url + self.url,
			"width": self.width,
			"height": self.height,
			"approved": self.approved,
			"created_at": self.created_at.isoformat(),
			"is_cover_image": self.package.cover_image == self,
		}

	def as_short_dict(self, base_url=""):
		return {
			"title": self.title,
			"url": base_url + self.url,
		}


class PackageUpdateTrigger(enum.Enum):
	COMMIT = "New Commit"
	TAG = "New Tag"

	def to_name(self):
		return self.name.lower()

	def __str__(self):
		return self.name

	@classmethod
	def get(cls, name):
		try:
			return PackageUpdateTrigger[name.upper()]
		except KeyError:
			return None

	@classmethod
	def choices(cls):
		return [(choice, choice.value) for choice in cls]

	@classmethod
	def coerce(cls, item):
		return item if type(item) == PackageUpdateTrigger else PackageUpdateTrigger[item.upper()]


class PackageUpdateConfig(db.Model):
	package_id  = db.Column(db.Integer, db.ForeignKey("package.id"), primary_key=True)
	package     = db.relationship("Package", back_populates="update_config", foreign_keys=[package_id])

	last_commit = db.Column(db.String(41), nullable=True, default=None)
	last_tag    = db.Column(db.String(41), nullable=True, default=None)

	# Set to now when an outdated notification is sent. Set to None when a release is created
	outdated_at = db.Column(db.DateTime, nullable=True, default=None)

	last_checked_at = db.Column(db.DateTime, nullable=True, default=None)

	trigger     = db.Column(db.Enum(PackageUpdateTrigger), nullable=False, default=PackageUpdateTrigger.COMMIT)
	ref         = db.Column(db.String(41), nullable=True, default=None)

	make_release = db.Column(db.Boolean, nullable=False, default=False)

	# Was this made using Add Update Configs in Admin?
	auto_created = db.Column(db.Boolean, nullable=False, default=False)

	def set_outdated(self):
		self.outdated_at = datetime.datetime.utcnow()

	def get_message(self):
		if self.trigger == PackageUpdateTrigger.COMMIT:
			msg = lazy_gettext("New commit %(hash)s found on the Git repo.", hash=self.last_commit[0:5])

			last_release = self.package.releases.first()
			if last_release and last_release.commit_hash:
				msg += " " + lazy_gettext("The last release was commit %(hash)s",
						hash=last_release.commit_hash[0:5])

			return msg

		else:
			return lazy_gettext("New tag %(tag_name)s found on the Git repo.", tag_name=self.last_tag)

	@property
	def title(self):
		return self.last_tag or self.outdated_at.strftime("%Y-%m-%d")

	def get_ref(self):
		return self.last_tag or self.last_commit

	def get_create_release_url(self):
		return self.package.get_url("packages.create_release", title=self.title, ref=self.get_ref())


class PackageAlias(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
	package    = db.relationship("Package", back_populates="aliases", foreign_keys=[package_id])

	author     = db.Column(db.String(50), nullable=False)
	name      = db.Column(db.String(100), nullable=False)

	def __init__(self, author="", name=""):
		self.author = author
		self.name = name

	def get_edit_url(self):
		return url_for("packages.alias_create_edit", author=self.package.author.username,
				name=self.package.name, alias_id=self.id)

	def as_dict(self):
		return f"{self.author}/{self.name}"


class PackageDailyStats(db.Model):
	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), primary_key=True)
	package = db.relationship("Package", back_populates="daily_stats", foreign_keys=[package_id])
	date = db.Column(db.Date, primary_key=True)

	platform_minetest = db.Column(db.Integer, nullable=False, default=0)
	platform_other = db.Column(db.Integer, nullable=False, default=0)

	reason_new = db.Column(db.Integer, nullable=False, default=0)
	reason_dependency = db.Column(db.Integer, nullable=False, default=0)
	reason_update = db.Column(db.Integer, nullable=False, default=0)

	@staticmethod
	def update(package: Package, is_luanti: bool, reason: str):
		date = datetime.datetime.utcnow().date()

		to_update = dict()
		kwargs = {
			"package_id": package.id, "date": date
		}

		field_platform = "platform_minetest" if is_luanti else "platform_other"
		to_update[field_platform] = getattr(PackageDailyStats, field_platform) + 1
		kwargs[field_platform] = 1

		field_reason = None
		if reason == "new":
			field_reason = "reason_new"
		elif reason == "dependency":
			field_reason = "reason_dependency"
		elif reason == "update":
			field_reason = "reason_update"

		if field_reason:
			to_update[field_reason] = getattr(PackageDailyStats, field_reason) + 1
			kwargs[field_reason] = 1

		stmt = insert(PackageDailyStats).values(**kwargs)
		stmt = stmt.on_conflict_do_update(
			index_elements=[PackageDailyStats.package_id, PackageDailyStats.date],
			set_=to_update
		)

		conn = db.session.connection()
		conn.execute(stmt)
