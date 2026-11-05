# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Imports a database dump made by `create_database_dump` in app/tasks/dumptask.py, for setting up an instance.

Users and packages that already exist are left unchanged.
"""

import datetime
import json
import os
import zipfile
from dataclasses import dataclass, field
from typing import Any, Optional

from app.models import db, User, Package, PackageType, PackageState, PackageDevState, PackageAIDisclosure, License, \
	Tag, ContentWarning, Language, MetaPackage, Dependency, PackageTranslation, PackageAlias, PackageRelease, \
	ReleaseState, PackageScreenshot, PackageGameSupport, LuantiRelease


SUPPORTED_VERSION = 1


class DumpImportError(Exception):
	pass


@dataclass
class ImportSummary:
	users_created: int = 0
	users_existing: int = 0
	packages_created: int = 0
	packages_existing: list[str] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)


def _parse_datetime(value: Optional[str]) -> Optional[datetime.datetime]:
	return datetime.datetime.fromisoformat(value) if value else None


def _upload_path(filename_or_url: str) -> str:
	return "/uploads/" + os.path.basename(filename_or_url)


class _Importer:
	def __init__(self, zipf: zipfile.ZipFile):
		self.zipf = zipf
		self.names = set(zipf.namelist())
		self.summary = ImportSummary()

		self.users: dict[str, User] = {x.username.lower(): x for x in User.query.all()}
		self.github_usernames = {x.github_username.lower() for x in self.users.values() if x.github_username}
		self.forums_usernames = {x.forums_username.lower() for x in self.users.values() if x.forums_username}
		self.packages: dict[tuple[str, str], Package] = {
			(x.author.username.lower(), x.name): x
			for x in Package.query.options(db.joinedload(Package.author)).all()
		}

		self.licenses = {x.name: x for x in License.query.all()}
		self.tags = {x.name: x for x in Tag.query.all()}
		self.content_warnings = {x.name: x for x in ContentWarning.query.all()}
		self.languages = {x.id: x for x in Language.query.all()}
		self.luanti_releases = {x.name: x for x in LuantiRelease.query.all()}
		self.meta_packages: dict[str, MetaPackage] = {}

		# Dump user data, by lowercase username
		self.dump_users: dict[str, dict[str, Any]] = {}

	def read_json(self, path: str) -> Any:
		try:
			return json.loads(self.zipf.read(path))
		except KeyError as e:
			raise DumpImportError(f"Missing {path}") from e
		except json.JSONDecodeError as e:
			raise DumpImportError(f"Invalid JSON in {path}: {e}") from e

	def read_json_if_exists(self, path: str, default: Any) -> Any:
		return self.read_json(path) if path in self.names else default

	def run(self) -> ImportSummary:
		index = self.read_json("backup/index.json")
		version = index.get("version") if isinstance(index, dict) else None
		if version != SUPPORTED_VERSION:
			raise DumpImportError(f"Unsupported dump version {version}, expected {SUPPORTED_VERSION}")

		self.import_lookup_tables()

		user_paths = sorted(x for x in self.names if x.count("/") == 2 and x.endswith("/index.json"))
		package_paths = sorted(x for x in self.names if x.count("/") == 3 and x.endswith("/index.json"))

		for path in user_paths:
			self.import_user(self.read_json(path))

		# User.__eq__ needs ids, and packages refer to users
		db.session.flush()

		created: list[tuple[Package, dict[str, Any]]] = []
		for path in package_paths:
			data = self.read_json(path)
			package = self.import_package(data, os.path.dirname(path))
			if package is not None:
				created.append((package, data))

		# Done after all packages exist, as these refer to other packages
		for package, data in created:
			self.import_relations(package, data)

		db.session.flush()
		return self.summary

	def import_lookup_tables(self):
		for row in self.read_json("backup/licenses.json"):
			if row["name"] not in self.licenses:
				license = License(row["name"], row["is_foss"], row["url"])
				db.session.add(license)
				self.licenses[license.name] = license

		for row in self.read_json("backup/tags.json"):
			if row["name"] not in self.tags:
				tag = Tag(row["title"], row["background_color"], row["text_color"])
				tag.name = row["name"]
				tag.description = row["description"]
				db.session.add(tag)
				self.tags[tag.name] = tag

		for row in self.read_json("backup/content_warnings.json"):
			if row["name"] not in self.content_warnings:
				warning = ContentWarning(row["title"], row["description"])
				warning.name = row["name"]
				db.session.add(warning)
				self.content_warnings[warning.name] = warning

		for row in self.read_json("backup/languages.json"):
			if row["id"] not in self.languages:
				language = Language()
				language.id = row["id"]
				language.title = row["title"]
				db.session.add(language)
				self.languages[language.id] = language

	def import_user(self, data: dict[str, Any]):
		username: str = data["username"]
		self.dump_users[username.lower()] = data

		if username.lower() in self.users:
			self.summary.users_existing += 1
			return

		# The rank in the dump is ignored. NOT_JOINED users can be claimed through their forum account
		user = User(username)
		user.display_name = data["display_name"]
		user.website_url = data.get("website_url")
		user.donate_url = data.get("donate_url")
		user.profile_pic = data.get("profile_pic_url")

		connections = data.get("connections") or {}
		github = connections.get("github")
		if github:
			if github.lower() in self.github_usernames:
				self.summary.warnings.append(f"{username}: GitHub username {github} is already used by another user")
			else:
				user.github_username = github
				self.github_usernames.add(github.lower())

		forums = connections.get("forums")
		if forums:
			if forums.lower() in self.forums_usernames:
				self.summary.warnings.append(f"{username}: forums username {forums} is already used by another user")
			else:
				user.forums_username = forums
				self.forums_usernames.add(forums.lower())

		db.session.add(user)
		self.users[username.lower()] = user
		self.summary.users_created += 1

	def get_user(self, username: str, context: str) -> Optional[User]:
		user = self.users.get(username.lower())
		if user is None:
			self.summary.warnings.append(f"{context}: user {username} isn't in the dump or the database")
		return user

	def get_license(self, name: str, context: str) -> License:
		license = self.licenses.get(name)
		if license is None:
			raise DumpImportError(f"{context}: unknown license {name}")
		return license

	def get_luanti_release(self, data: Optional[dict[str, Any]]) -> Optional[LuantiRelease]:
		if not data:
			return None

		release = self.luanti_releases.get(data["name"])
		if release is None:
			release = LuantiRelease(data["name"], data["protocol_version"])
			db.session.add(release)
			self.luanti_releases[release.name] = release
		return release

	def import_package(self, data: dict[str, Any], prefix: str) -> Optional[Package]:
		author_name: str = data["author"]
		name: str = data["name"]
		context = f"{author_name}/{name}"

		if (author_name.lower(), name) in self.packages:
			self.summary.packages_existing.append(context)
			return None

		author = self.users.get(author_name.lower())
		if author is None:
			raise DumpImportError(f"{context}: author isn't in the dump or the database")

		package_type = PackageType.get(data["type"])
		state = PackageState.get(data["state"])
		if package_type is None or state is None:
			raise DumpImportError(f"{context}: unknown type {data['type']} or state {data['state']}")

		package = Package()
		package.author = author
		package.name = name
		package.title = data["title"]
		package.short_desc = data["short_description"]
		package.desc = data.get("long_description")
		package.type = package_type
		package.state = state
		package.dev_state = PackageDevState.get(data["dev_state"]) if data.get("dev_state") else None
		package.ai_disclosure = (PackageAIDisclosure.get(data["ai_disclosure"]) if data.get("ai_disclosure") else None) \
				or PackageAIDisclosure.UNKNOWN
		package.created_at = _parse_datetime(data["created_at"])
		package.approved_at = _parse_datetime(data.get("approved_at"))
		package.license = self.get_license(data["license"], context)
		package.media_license = self.get_license(data["media_license"], context)

		package.repo = data.get("repo")
		package.website = data.get("website")
		package.issueTracker = data.get("issue_tracker")
		package.forums = data.get("forums")
		package.video_url = data.get("video_url")
		package.translation_url = data.get("translation_url")

		# The dump has the donate URL shown on the page, which falls back to the author's
		author_donate_url = (self.dump_users.get(author_name.lower()) or {}).get("donate_url")
		donate_url = data.get("donate_url")
		package.donate_url = donate_url if donate_url != author_donate_url else None

		package.downloads = data.get("downloads", 0)
		package.score = data.get("score", 0)
		package.score_downloads = data.get("score_downloads", package.score)
		package.supports_all_games = data.get("supports_all_games", False)

		for tag_name in data.get("tags", []):
			tag = self.tags.get(tag_name)
			if tag is None:
				raise DumpImportError(f"{context}: unknown tag {tag_name}")
			package.tags.append(tag)

		for warning_name in data.get("content_warnings", []):
			warning = self.content_warnings.get(warning_name)
			if warning is None:
				raise DumpImportError(f"{context}: unknown content warning {warning_name}")
			package.content_warnings.append(warning)

		for username in sorted(set(data.get("maintainers", []))):
			maintainer = self.get_user(username, context)
			if maintainer is not None:
				package.maintainers.append(maintainer)

		for meta_name in data.get("provides", []):
			package.provides.append(MetaPackage.GetOrCreate(meta_name, self.meta_packages))

		for language_id, translation_data in data.get("translations", {}).items():
			if language_id not in self.languages:
				self.summary.warnings.append(f"{context}: skipped translation to unknown language {language_id}")
				continue

			translation = PackageTranslation()
			translation.package = package
			translation.language_id = language_id
			translation.title = translation_data.get("title")
			translation.short_desc = translation_data.get("short_desc")
			translation.desc = translation_data.get("desc")
			db.session.add(translation)

		for alias_data in data.get("aliases", []):
			package.aliases.append(PackageAlias(alias_data["author"], alias_data["name"]))

		db.session.add(package)
		self.packages[(author_name.lower(), name)] = package

		self.import_releases(package, self.read_json_if_exists(f"{prefix}/releases.json", []), context)
		self.import_screenshots(package, self.read_json_if_exists(f"{prefix}/screenshots.json", []))

		self.summary.packages_created += 1
		return package

	def import_releases(self, package: Package, releases: list[dict[str, Any]], context: str):
		for data in releases:
			if not data.get("url"):
				self.summary.warnings.append(f"{context}: skipped release {data.get('name')} without a file")
				continue

			release = PackageRelease()
			release.package = package
			release.name = data["name"]
			release.title = data["title"]
			release.release_notes = data.get("release_notes")
			release.upload_path = _upload_path(data["url"])
			release.created_at = _parse_datetime(data["release_date"])
			release.commit_hash = data.get("commit")
			release.downloads = data.get("downloads", 0)
			release.file_size_bytes = data.get("size") or 0
			release.file_sha256 = data.get("sha256")
			release.min_rel = self.get_luanti_release(data.get("min_minetest_version"))
			release.max_rel = self.get_luanti_release(data.get("max_minetest_version"))
			release.task_id = None
			release.state = ReleaseState.APPROVED
			db.session.add(release)

	def import_screenshots(self, package: Package, screenshots: list[dict[str, Any]]):
		for data in screenshots:
			screenshot = PackageScreenshot()
			screenshot.package = package
			screenshot.title = data["title"]
			screenshot.order = data["order"]
			screenshot.upload_path = _upload_path(data["filename"])
			screenshot.width = data["width"]
			screenshot.height = data["height"]
			screenshot.file_size_bytes = data.get("file_size_bytes", 0)
			screenshot.created_at = _parse_datetime(data["created_at"])
			screenshot.approved = True
			db.session.add(screenshot)

			if data.get("is_cover_image"):
				package.cover_image = screenshot

	def import_relations(self, package: Package, data: dict[str, Any]):
		context = f"{data['author']}/{data['name']}"

		for key, optional in [("depends", False), ("optional_depends", True)]:
			for name in data.get(key, []):
				meta = MetaPackage.GetOrCreate(name, self.meta_packages)
				db.session.add(Dependency(package, meta=meta, optional=optional))

		for support_data in data.get("game_support", []):
			game_data = support_data["game"]
			game = self.packages.get((game_data["author"].lower(), game_data["name"]))
			if game is None:
				self.summary.warnings.append(
						f"{context}: skipped support for game {game_data['author']}/{game_data['name']}, which doesn't exist")
				continue

			support = PackageGameSupport()
			support.package = package
			support.game = game
			support.supports = support_data["supports"]
			support.confidence = support_data["confidence"]
			db.session.add(support)


def import_dump(zip_path: str) -> ImportSummary:
	"""
	Adds the dump's contents to the session, without committing. Raises DumpImportError if the dump is invalid.
	"""
	try:
		zipf = zipfile.ZipFile(zip_path)
	except zipfile.BadZipFile as e:
		raise DumpImportError(f"Not a valid zip file: {e}") from e

	# Lookups like MetaPackage.GetOrCreate would otherwise flush rows that are still being filled in
	with zipf, db.session.no_autoflush:
		return _Importer(zipf).run()
