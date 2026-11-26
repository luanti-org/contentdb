# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Optional, List
from flask import abort, current_app, has_request_context, request, make_response
from flask_babel import lazy_gettext, gettext, get_locale
from sqlalchemy import or_, and_, false
from sqlalchemy.orm import joinedload, load_only, selectinload
from sqlalchemy.sql import Subquery
from sqlalchemy.sql.expression import func
from sqlalchemy_searchable import search
from urllib.parse import urlparse

from .models import db, PackageType, Package, ForumTopic, License, LuantiRelease, PackageRelease, User, Tag, \
	ContentWarning, PackageState, PackageDevState, ReleaseState, PackageAIDisclosure, PackageTranslation, Collection, \
	CollectionPackage
from app.utils.misc import is_yes


class QueryBuilder:
	emit_http_errors: bool
	limit: Optional[int]
	lang: str = "en"
	types: List[PackageType]
	search: Optional[str] = None
	only_approved: bool = True
	licenses: List[License]
	tags: List[Tag]
	hide_tags: List[Tag]
	game: Optional[Package]
	collection: Optional[Collection]
	# A collection was given but doesn't exist or is private. Without emit_http_errors, this matches no packages.
	collection_missing: bool = False
	# A filter refers to something that doesn't exist, such as a deleted game, collection, or author. Only happens
	# without emit_http_errors, such as for homepage widgets, where a stale query should show nothing rather than
	# everything or an error.
	match_nothing: bool = False
	author: Optional[str]
	random: bool
	lucky: bool
	order_dir: str
	order_by: Optional[str]
	# Whether sort or order was given in the URL, rather than defaulted
	explicit_order: bool
	flags: set[str]
	hide_flags: set[str]
	hide_deprecated: bool
	hide_wip: bool
	show_added: Optional[bool]
	version: Optional[LuantiRelease]
	not_version: Optional[LuantiRelease]
	has_lang: Optional[str]
	# Set by build_package_query when sorting by last_release, for order_package_query
	_last_release: Optional[Subquery] = None

	@property
	def title(self):
		if len(self.types) == 1:
			package_type = str(self.types[0].plural)
		else:
			package_type = lazy_gettext("Packages")

		if len(self.tags) == 0:
			ret = package_type
		elif len(self.tags) == 1:
			ret = self.tags[0].get_translated()["title"] + " " + package_type
		else:
			tags = ", ".join([tag.get_translated()["title"] for tag in self.tags])
			ret = f"{tags} - {package_type}"

		if self.search:
			ret = f"{self.search} - {ret}"

		if self.game:
			meta = self.game.get_translated(load_desc=False)
			ret = gettext("%(package_type)s for %(game_name)s", package_type=ret, game_name=meta["title"])

		if self.collection:
			ret = gettext("%(package_type)s in %(collection)s", package_type=ret, collection=self.collection.title)

		return ret

	@property
	def query_hint(self):
		return self.title

	@property
	def noindex(self):
		return (self.search is not None or len(self.tags) > 1 or len(self.flags) > 1 or len(self.types) > 1 or
			len(self.licenses) > 0 or len(self.hide_flags) > 0 or len(self.hide_tags) > 0 or self.random or
			self.lucky or self.author or self.version or self.not_version or self.game or self.collection or
			self.match_nothing or self.limit is not None or self.explicit_order)

	@property
	def requires_login(self):
		return len(self.tags) > 1

	VALID_SORTS = {"score", "reviews", "name", "title", "downloads", "created_at", "date", "approved_at", "last_release",
			"collection"}

	def _error(self, message: str, code: int = 400):
		"""Aborts with a message if emit_http_errors, otherwise returns so the caller can fall back"""
		if self.emit_http_errors:
			abort(make_response(message, code))

	def _get_int(self, args, name: str) -> Optional[int]:
		value = args.get(name)
		if value is None or value == "":
			return None

		try:
			return int(value)
		except ValueError:
			self._error(f"{name} must be an integer")
			return None

	def __init__(self, args, cookies: bool = False, lang: Optional[str] = None, emit_http_errors: bool = True):
		self.emit_http_errors = emit_http_errors

		# Block bots that encode incorrectly. Only checks the request's own query string, as args may come from
		# elsewhere, such as a homepage widget's stored query.
		if has_request_context() and args is request.args:
			query_str = urlparse(request.url).query
			if "&amp" in query_str:
				abort(400)

		if lang is None:
			locale = get_locale()
			if locale:
				self.lang = locale.language
		else:
			self.lang = lang

		# Get request types
		types = args.getlist("type")
		types = [PackageType.get(tname) for tname in types]
		if any([type is None for type in types]):
			self._error("Unknown type")
			# Types are OR-ed, so only match nothing if none of them exist
			if all([type is None for type in types]):
				self.match_nothing = True
			types = [type for type in types if type is not None]

		# Get tags types
		tags = args.getlist("tag")
		tags = [Tag.query.filter_by(name=tname).first() for tname in tags]
		if any([tag is None for tag in tags]):
			self._error("Unknown tag")
			# Tags are AND-ed, so no package has a tag that doesn't exist
			self.match_nothing = True
			tags = [tag for tag in tags if tag is not None]

		# Hide
		self.hide_flags = set(args.getlist("hide"))

		self.hide_tags = []
		for flag in set(self.hide_flags):
			tag = Tag.query.filter_by(name=flag).first()
			if tag is not None:
				self.hide_tags.append(tag)
				self.hide_flags.remove(flag)

		# Show flags
		self.flags = set(args.getlist("flag"))

		# License
		licenses = [License.query.filter(func.lower(License.name) == name.lower()).first() for name in args.getlist("license")]
		if any(map(lambda x: x is None, licenses)):
			if emit_http_errors:
				all_licenses = db.session.query(License.name).order_by(db.asc(License.name)).all()
				all_licenses = [x[0] for x in all_licenses]
				self._error("Unknown license. Expected license name from: " + ", ".join(all_licenses))
			# Licenses are OR-ed, so only match nothing if none of them exist
			if all(map(lambda x: x is None, licenses)):
				self.match_nothing = True
		self.licenses = [x for x in licenses if x is not None]

		self.types  = types
		self.tags   = tags

		self.random = "random" in args
		self.lucky  = "lucky" in args
		self.limit  = 1 if self.lucky else self._get_int(args, "limit")
		self.explicit_order = bool(args.get("sort") or args.get("order"))
		self.order_by  = args.get("sort")
		if self.order_by == "":
			self.order_by = None
		if self.order_by is not None and self.order_by not in self.VALID_SORTS:
			self._error("Unknown sort. Expected one of: " + ", ".join(sorted(self.VALID_SORTS)))
			self.order_by = None
		self.order_dir = args.get("order") or "desc"
		if self.order_dir not in ("asc", "desc"):
			self._error("order must be asc or desc")
			self.order_dir = "desc"

		if "android_default" in self.hide_flags:
			self.hide_flags.update(["*", "deprecated"])
			self.hide_flags.discard("android_default")

		if "desktop_default" in self.hide_flags:
			self.hide_flags.update(["deprecated"])
			self.hide_flags.discard("desktop_default")

		self.hide_wip = "wip" in self.hide_flags
		self.hide_deprecated = "deprecated" in self.hide_flags
		self.hide_flags.discard("nonfree")
		self.hide_flags.discard("wip")
		self.hide_flags.discard("deprecated")

		# Filters
		self.search = args.get("q")
		self.author = args.get("author")

		protocol_version = self._get_int(args, "protocol_version")
		engine_version = args.get("engine_version")
		invert_version = "not_supported" in args
		if engine_version == "":
			engine_version = None

		if protocol_version or engine_version:
			version = LuantiRelease.get(engine_version, protocol_version)
		else:
			version = None

		if invert_version:
			self.not_version = version
			self.version = None
		else:
			self.version = version
			self.not_version = None

		show_added = args.get("show_added")
		self.show_added = is_yes(show_added) if show_added is not None else None

		if self.search is not None and self.search.strip() == "":
			self.search = None

		self.game = args.get("game")
		if self.game:
			self.game = Package.get_by_key(self.game)
			if self.game is None:
				self._error("Unable to find that game")
				self.match_nothing = True
		else:
			self.game = None

		self.collection = None
		collection_key = args.get("collection")
		if collection_key:
			self.collection = self.get_collection(collection_key)
			if self.collection is None:
				self._error("Unable to find that collection")
				self.collection_missing = True
				self.match_nothing = True

		if self.order_by == "collection" and not (self.collection or self.collection_missing):
			self._error("sort=collection needs a collection")
			self.order_by = None

		# Collections are listed in their curated order, unless another sort is asked for
		if (self.collection or self.collection_missing) and self.order_by is None and not self.search and \
				not self.random:
			self.order_by = "collection"
		if self.order_by == "collection" and "order" not in args:
			self.order_dir = "asc"

		self.has_lang = args.get("lang")
		if self.has_lang == "":
			self.has_lang = None

	@staticmethod
	def get_collection(key: str) -> Optional[Collection]:
		"""Finds a public collection from author/name"""
		parts = key.split("/")
		if len(parts) != 2:
			return None

		author, name = parts
		return Collection.query.filter(
				Collection.name == name,
				Collection.author.has(username=author),
				Collection.private.is_(False)).first()

	def set_sort_if_none(self, name, dir="desc"):
		if self.order_by is None:
			self.order_by = name
			self.order_dir = dir

	def get_releases(self):
		releases_query = db.session.query(PackageRelease.package_id, func.max(PackageRelease.id)) \
			.select_from(PackageRelease).filter(PackageRelease.state == ReleaseState.APPROVED) \
			.group_by(PackageRelease.package_id)

		if self.version:
			releases_query = releases_query \
				.filter(or_(PackageRelease.min_rel_id==None,
					PackageRelease.min_rel_id <= self.version.id)) \
				.filter(or_(PackageRelease.max_rel_id==None,
					PackageRelease.max_rel_id >= self.version.id))

		return releases_query.all()

	def convert_to_dictionary(self, packages, include_vcs: bool):
		releases = {}
		for [package_id, release_id] in self.get_releases():
			releases[package_id] = release_id

		translations = {}
		if self.lang != "en" and len(packages) > 0:
			package_ids = [package.id for package in packages]
			for translation in PackageTranslation.query \
					.filter(PackageTranslation.language_id == self.lang,
						PackageTranslation.package_id.in_(package_ids)).all():
				translations[translation.package_id] = translation

		def to_json(package: Package):
			release_id = releases.get(package.id)
			return package.as_short_dict(current_app.config["BASE_URL"], release_id=release_id, no_load=True,
					lang=self.lang, include_vcs=include_vcs, translation=translations.get(package.id),
					translations_prefetched=self.lang != "en")

		return [to_json(pkg) for pkg in packages]

	def build_package_query(self, for_tiles: bool = False):
		query = Package.query
		if self.order_by == "last_release":
			# One row per package, so packages with several releases aren't listed more than once.
			# Packages without an approved release are left out.
			self._last_release = (db.session.query(
						PackageRelease.package_id,
						func.max(PackageRelease.created_at).label("created_at"))
					.filter(PackageRelease.state == ReleaseState.APPROVED)
					.group_by(PackageRelease.package_id)
					.subquery())
			query = query.join(self._last_release, self._last_release.c.package_id == Package.id)
		elif self.order_by == "collection" and self.collection:
			query = query.join(CollectionPackage, and_(
					CollectionPackage.package_id == Package.id,
					CollectionPackage.collection_id == self.collection.id))

		if self.only_approved:
			query = query.filter(Package.state == PackageState.APPROVED)

		# selectinload rather than subqueryload: subqueryload re-runs the main query, which picks different
		# packages when it's ordered by random(), so they'd be missing their screenshots
		if for_tiles:
			query = query.options(
				load_only(Package.name, Package.title, Package.short_desc, Package.state, raiseload=True),
				joinedload(Package.author).load_only(User.username, User.display_name, raiseload=True),
				selectinload(Package.main_screenshot),
			)
		else:
			query = query.options(
				joinedload(Package.author),
				selectinload(Package.main_screenshot),
				selectinload(Package.aliases),
			)

		query = self.order_package_query(self.filter_package_query(query))

		if self.limit:
			query = query.limit(self.limit)

		return query

	def filter_package_query(self, query):
		if len(self.types) > 0:
			query = query.filter(Package.type.in_(self.types))

		if self.author:
			author = User.query.filter_by(username=self.author).first()
			if author:
				query = query.filter_by(author=author)
			else:
				self._error("Unable to find that author", 404)
				query = query.filter(false())

		if self.game:
			query = query.filter(Package.supported_games.any(game=self.game, supports=True))

		if self.collection:
			query = query.filter(Package.collections.any(Collection.id == self.collection.id))

		if self.match_nothing:
			query = query.filter(false())

		if self.has_lang and self.has_lang != "en":
			query = query.filter(Package.translations.any(language_id=self.has_lang))

		for tag in self.tags:
			query = query.filter(Package.tags.contains(tag))

		for tag in self.hide_tags:
			query = query.filter(~Package.tags.contains(tag))

		if "genai" in self.hide_flags or "anyai" in self.hide_flags:
			self.hide_flags.discard("genai")
			query = query.filter(Package.ai_disclosure != PackageAIDisclosure.GENERATED)

			if "anyai" in self.hide_flags:
				self.hide_flags.discard("anyai")
				query = query.filter(Package.ai_disclosure != PackageAIDisclosure.ASSISTED)

		if "*" in self.hide_flags:
			query = query.filter(~ Package.content_warnings.any())
		else:
			for flag in self.hide_flags:
				warning = ContentWarning.query.filter_by(name=flag).first()
				if warning:
					query = query.filter(~ Package.content_warnings.any(ContentWarning.id == warning.id))
				else:
					# Hiding something that doesn't exist hides nothing, so this can be ignored without emit_http_errors
					self._error("Unknown tag or content warning " + flag)

		flags = set(self.flags)
		flags.discard("nonfree")
		if "wip" in flags:
			query = query.filter(Package.dev_state == PackageDevState.WIP)
			flags.discard("wip")
		if "deprecated" in flags:
			query = query.filter(Package.dev_state == PackageDevState.DEPRECATED)
			flags.discard("deprecated")

		if "*" in flags:
			query = query.filter(Package.content_warnings.any())
			flags.discard("*")
		else:
			for flag in flags:
				warning = ContentWarning.query.filter_by(name=flag).first()
				if warning:
					query = query.filter(Package.content_warnings.any(ContentWarning.id == warning.id))

		licenses = [Package.license_id == license.id for license in self.licenses if license is not None]
		licenses.extend([Package.media_license_id == license.id for license in self.licenses if license is not None])
		if len(licenses) > 0:
			query = query.filter(or_(*licenses))

		if self.hide_wip:
			query = query.filter(or_(Package.dev_state==None, Package.dev_state != PackageDevState.WIP))
		if self.hide_deprecated:
			query = query.filter(or_(Package.dev_state==None, Package.dev_state != PackageDevState.DEPRECATED))

		if self.version:
			query = query.filter(Package.releases.any(and_(or_(PackageRelease.min_rel_id==None,
					PackageRelease.min_rel_id <= self.version.id), or_(PackageRelease.max_rel_id==None,
					PackageRelease.max_rel_id >= self.version.id))))
		elif self.not_version:
			query = query.filter(~Package.releases.any(and_(or_(PackageRelease.min_rel_id==None,
					PackageRelease.min_rel_id <= self.not_version.id), or_(PackageRelease.max_rel_id==None,
					PackageRelease.max_rel_id >= self.not_version.id))))

		return query

	def order_package_query(self, query):
		if self.search:
			query = search(query, self.search, sort=self.order_by is None)

		if self.random:
			query = query.order_by(func.random())
			return query

		to_order = None
		if self.order_by is None and self.search:
			pass
		elif self.order_by is None or self.order_by == "score":
			to_order = Package.score
		elif self.order_by == "reviews":
			query = query.filter(Package.reviews.any(approved=True))
			to_order = (Package.score - Package.score_downloads)
		elif self.order_by == "name":
			to_order = Package.name
		elif self.order_by == "title":
			to_order = Package.title
		elif self.order_by == "downloads":
			to_order = Package.downloads
		elif self.order_by == "created_at" or self.order_by == "date":
			to_order = Package.created_at
		elif self.order_by == "approved_at" or self.order_by == "date":
			to_order = Package.approved_at
		elif self.order_by == "last_release":
			assert self._last_release is not None, "last_release requires the query from build_package_query"
			to_order = self._last_release.c.created_at
		elif self.order_by == "collection":
			# __init__ makes sure there's a collection. If it's missing, the query matches nothing anyway.
			if self.collection:
				to_order = CollectionPackage.order
		else:
			abort(400)

		if to_order is not None:
			if self.order_dir == "asc":
				to_order = db.asc(to_order)
			elif self.order_dir == "desc":
				to_order = db.desc(to_order)
			else:
				abort(400)

			query = query.order_by(to_order)

		return query

	def build_topic_query(self, show_added=False):
		query = ForumTopic.query

		show_added = self.show_added == True or (self.show_added is None and show_added)
		if not show_added:
			query = query.filter(~ db.exists().where(Package.forums==ForumTopic.topic_id))

		if self.order_by is None or self.order_by == "name":
			query = query.order_by(db.asc(ForumTopic.wip), db.asc(ForumTopic.name), db.asc(ForumTopic.title))
		elif self.order_by == "views":
			query = query.order_by(db.desc(ForumTopic.views))
		elif self.order_by == "created_at" or self.order_by == "date":
			query = query.order_by(db.asc(ForumTopic.created_at))

		if self.search:
			query = query.filter(or_(ForumTopic.title.ilike('%' + self.search + '%'),
					ForumTopic.name == self.search.lower()))

		if len(self.types) > 0:
			query = query.filter(ForumTopic.type.in_(self.types))

		if self.limit:
			query = query.limit(self.limit)

		return query
