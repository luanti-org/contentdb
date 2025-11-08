# ContentDB
# Copyright (C) rubenwardy
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

from typing import Optional, List
from flask import abort, current_app, request, make_response
from flask_babel import lazy_gettext, gettext, get_locale
from sqlalchemy import or_, and_
from sqlalchemy.orm import subqueryload
from sqlalchemy.sql.expression import func
from sqlalchemy_searchable import search

from .models import db, PackageType, Package, ForumTopic, License, LuantiRelease, PackageRelease, User, Tag, \
	ContentWarning, PackageState, PackageDevState, ReleaseState
from .utils import is_yes, get_int_or_abort


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
	author: Optional[str]
	random: bool
	lucky: bool
	order_dir: str
	order_by: Optional[str]
	flags: set[str]
	hide_flags: set[str]
	hide_deprecated: bool
	hide_wip: bool
	hide_nonfree: bool
	show_added: bool
	version: Optional[LuantiRelease]
	has_lang: Optional[str]

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

		return ret

	@property
	def query_hint(self):
		return self.title

	@property
	def noindex(self):
		return (self.search is not None or len(self.tags) > 1 or len(self.flags) > 1 or len(self.types) > 1 or
			len(self.licenses) > 0 or len(self.hide_flags) > 0 or len(self.hide_tags) > 0 or self.random or
			self.lucky or self.author or self.version or self.game or self.limit is not None)

	def __init__(self, args, cookies: bool = False, lang: Optional[str] = None, emit_http_errors: bool = True):
		self.emit_http_errors = emit_http_errors

		if lang is None:
			locale = get_locale()
			if locale:
				self.lang = locale.language
		else:
			self.lang = lang

		# Get request types
		types = args.getlist("type")
		types = [PackageType.get(tname) for tname in types]
		if not emit_http_errors:
			types = [type for type in types if type is not None]
		elif any([type is None for type in types]):
			abort(make_response("Unknown type"), 400)

		# Get tags types
		tags = args.getlist("tag")
		tags = [Tag.query.filter_by(name=tname).first() for tname in tags]
		if not emit_http_errors:
			tags = [tag for tag in tags if tag is not None]
		elif any([tag is None for tag in tags]):
			abort(make_response("Unknown tag"), 400)

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
		self.licenses = [License.query.filter(func.lower(License.name) == name.lower()).first() for name in args.getlist("license")]
		if emit_http_errors and any(map(lambda x: x is None, self.licenses)):
			all_licenses = db.session.query(License.name).order_by(db.asc(License.name)).all()
			all_licenses = [x[0] for x in all_licenses]
			abort(make_response("Unknown license. Expected license name from: " + ", ".join(all_licenses)), 400)

		self.types  = types
		self.tags   = tags

		self.random = "random" in args
		self.lucky  = "lucky" in args
		self.limit  = 1 if self.lucky else get_int_or_abort(args.get("limit"), None)
		self.order_by  = args.get("sort")
		if self.order_by == "":
			self.order_by = None
		self.order_dir = args.get("order") or "desc"

		if "android_default" in self.hide_flags:
			self.hide_flags.update(["*", "deprecated"])
			self.hide_flags.discard("android_default")

		if "desktop_default" in self.hide_flags:
			self.hide_flags.update(["deprecated"])
			self.hide_flags.discard("desktop_default")

		self.hide_nonfree = "nonfree" in self.hide_flags
		self.hide_wip = "wip" in self.hide_flags
		self.hide_deprecated = "deprecated" in self.hide_flags
		self.hide_flags.discard("nonfree")
		self.hide_flags.discard("wip")
		self.hide_flags.discard("deprecated")

		# Filters
		self.search = args.get("q")
		self.author = args.get("author")

		protocol_version = get_int_or_abort(args.get("protocol_version"))
		engine_version = args.get("engine_version")
		if engine_version == "":
			engine_version = None

		if protocol_version or engine_version:
			self.version = LuantiRelease.get(engine_version, protocol_version)
		else:
			self.version = None

		self.show_added = args.get("show_added")
		if self.show_added is not None:
			self.show_added = is_yes(self.show_added)

		if self.search is not None and self.search.strip() == "":
			self.search = None

		self.game = args.get("game")
		if self.game:
			self.game = Package.get_by_key(self.game)
			if self.game is None:
				abort(make_response("Unable to find that game"), 400)
		else:
			self.game = None

		self.has_lang = args.get("lang")
		if self.has_lang == "":
			self.has_lang = None

		if cookies and request.cookies.get("hide_nonfree") == "1":
			self.hide_nonfree = True

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

		def to_json(package: Package):
			release_id = releases.get(package.id)
			return package.as_short_dict(current_app.config["BASE_URL"], release_id=release_id, no_load=True,
					lang=self.lang, include_vcs=include_vcs)

		return [to_json(pkg) for pkg in packages]

	def build_package_query(self):
		if self.order_by == "last_release":
			query = db.session.query(Package).select_from(PackageRelease).join(Package)
		else:
			query = Package.query

		if self.only_approved:
			query = query.filter(Package.state == PackageState.APPROVED)

		query = query.options(subqueryload(Package.main_screenshot), subqueryload(Package.aliases))

		query = self.order_package_query(self.filter_package_query(query))

		if self.limit:
			query = query.limit(self.limit)

		return query

	def filter_package_query(self, query):
		if len(self.types) > 0:
			query = query.filter(Package.type.in_(self.types))

		if self.author:
			author = User.query.filter_by(username=self.author).first()
			if not author:
				abort(404)

			query = query.filter_by(author=author)

		if self.game:
			query = query.filter(Package.supported_games.any(game=self.game, supports=True))

		if self.has_lang and self.has_lang != "en":
			query = query.filter(Package.translations.any(language_id=self.has_lang))

		for tag in self.tags:
			query = query.filter(Package.tags.contains(tag))

		for tag in self.hide_tags:
			query = query.filter(~Package.tags.contains(tag))

		if "*" in self.hide_flags:
			query = query.filter(~ Package.content_warnings.any())
		else:
			for flag in self.hide_flags:
				warning = ContentWarning.query.filter_by(name=flag).first()
				if warning:
					query = query.filter(~ Package.content_warnings.any(ContentWarning.id == warning.id))
				elif self.emit_http_errors:
					abort(make_response("Unknown tag or content warning " + flag), 400)

		flags = set(self.flags)
		if "nonfree" in flags:
			query = query.filter(or_(Package.license.has(is_foss=False), Package.media_license.has(is_foss=False)))
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

		if self.hide_nonfree:
			query = query.filter(Package.license.has(License.is_foss == True))
			query = query.filter(Package.media_license.has(License.is_foss == True))

		if self.hide_wip:
			query = query.filter(or_(Package.dev_state==None, Package.dev_state != PackageDevState.WIP))
		if self.hide_deprecated:
			query = query.filter(or_(Package.dev_state==None, Package.dev_state != PackageDevState.DEPRECATED))

		if self.version:
			query = query.filter(Package.releases.any(and_(or_(PackageRelease.min_rel_id==None,
					PackageRelease.min_rel_id <= self.version.id), or_(PackageRelease.max_rel_id==None,
					PackageRelease.max_rel_id >= self.version.id))))

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
			query = query.filter(Package.reviews.any())
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
			to_order = PackageRelease.created_at
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
