# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from collections import defaultdict
from typing import Any

from sqlalchemy import or_

from . import celery
from app import app
from app.models import User, Package, PackageState, Dependency, db, License, Tag, ContentWarning, Language, \
	PackageTranslation, PackageAlias, PackageScreenshot, PackageRelease, ReleaseState
import json
import os
import zipfile
import datetime
from app.uploads import copy_to_uploads
from app.utils.files import get_temp_dir


# Increase this when the dump format changes in a way that importers need to know about
DUMP_FORMAT_VERSION = 1


def get_dependency_names() -> dict[int, dict[str, list[str]]]:
	"""
	Returns the hard and optional dependencies of every package as mod names, keyed by package id.
	Loaded in one query, rather than one per package.
	"""
	names: dict[int, dict[str, set[str]]] = {}
	dependencies = Dependency.query \
		.options(db.joinedload(Dependency.meta_package), db.joinedload(Dependency.package)) \
		.filter(Dependency.depender_id.is_not(None)).all()
	for dep in dependencies:
		key = "optional_depends" if dep.optional else "depends"
		names.setdefault(dep.depender_id, {"depends": set(), "optional_depends": set()})[key].add(dep.get_name())

	return {
		package_id: {key: sorted(values) for key, values in deps.items()}
		for package_id, deps in names.items()
	}


def get_lookup_tables() -> dict[str, list[dict[str, Any]]]:
	"""
	Tables that packages refer to by name. Raw values are used rather than as_dict(), which translates them.
	"""
	return {
		"licenses": [{"name": x.name, "is_foss": x.is_foss, "url": x.url}
				for x in License.query.order_by(License.name).all()],
		"tags": [{"name": x.name, "title": x.title, "description": x.description,
				"background_color": x.backgroundColor, "text_color": x.textColor}
				for x in Tag.query.order_by(Tag.name).all()],
		"content_warnings": [{"name": x.name, "title": x.title, "description": x.description}
				for x in ContentWarning.query.order_by(ContentWarning.name).all()],
		"languages": [{"id": x.id, "title": x.title} for x in Language.query.order_by(Language.id).all()],
	}


def get_translations() -> dict[int, dict[str, dict[str, str | None]]]:
	"""Returns {package_id: {language_id: {title, short_desc, desc}}}"""
	ret: dict[int, dict[str, dict[str, str | None]]] = defaultdict(dict)
	for x in PackageTranslation.query.order_by(PackageTranslation.language_id).all():
		ret[x.package_id][x.language_id] = {"title": x.title, "short_desc": x.short_desc, "desc": x.desc}
	return ret


def get_aliases() -> dict[int, list[dict[str, str]]]:
	"""Returns {package_id: [{author, name}]}, the old names that redirect to each package"""
	ret: dict[int, list[dict[str, str]]] = defaultdict(list)
	for x in PackageAlias.query.order_by(PackageAlias.id).all():
		ret[x.package_id].append({"author": x.author, "name": x.name})
	return ret


def get_screenshots() -> dict[int, list[PackageScreenshot]]:
	"""Returns {package_id: [screenshot]}, only including approved screenshots"""
	ret: dict[int, list[PackageScreenshot]] = defaultdict(list)
	for x in PackageScreenshot.query.filter_by(approved=True) \
			.order_by(PackageScreenshot.order, PackageScreenshot.id).all():
		ret[x.package_id].append(x)
	return ret


def screenshot_as_dict(screenshot: PackageScreenshot, package: Package) -> dict[str, Any]:
	return {
		"title": screenshot.title,
		"order": screenshot.order,
		"filename": os.path.basename(screenshot.upload_path),
		"url": screenshot.public_url,
		"width": screenshot.width,
		"height": screenshot.height,
		"file_size_bytes": screenshot.file_size_bytes,
		"created_at": screenshot.created_at.isoformat(),
		"is_cover_image": package.cover_image_id == screenshot.id,
	}


@celery.task()
def create_database_dump():
	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	base_url = app.config["BASE_URL"]
	with get_temp_dir() as tmp_dir:
		tmp_path = os.path.join(tmp_dir, f"backup-{date}.zip")
		with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zipf:
			zipf.writestr("backup/index.json", json.dumps({
				"version": DUMP_FORMAT_VERSION,
				"created_at": datetime.datetime.utcnow().isoformat(),
			}, indent=4))

			for name, rows in get_lookup_tables().items():
				zipf.writestr(f"backup/{name}.json", json.dumps(rows, indent=4))

			# Maintainers are included too, so every username in `maintainers` has an index.json
			users = User.query.filter(or_(
					User.packages.any(state=PackageState.APPROVED),
					User.maintained_packages.any(state=PackageState.APPROVED))).all()
			for user in users:
				content = json.dumps(user.get_dict(), indent=4)
				zipf.writestr(f"backup/{user.username}/index.json", content)

			dependency_names = get_dependency_names()
			no_dependencies: dict[str, list[str]] = {"depends": [], "optional_depends": []}
			translations = get_translations()
			aliases = get_aliases()
			screenshots = get_screenshots()

			packages = Package.query.filter_by(state=PackageState.APPROVED).all()
			for package in packages:
				package_screenshots = screenshots.get(package.id, [])

				# as_dict already includes `provides`
				data = package.as_dict(base_url=base_url)
				data.update(dependency_names.get(package.id, no_dependencies))
				data["translations"] = translations.get(package.id, {})
				data["aliases"] = aliases.get(package.id, [])

				# `score` includes reviews, which aren't in the dump, so importers need this to recalculate it
				data["score_downloads"] = package.score_downloads

				# as_dict includes unapproved screenshots, and games that aren't in the dump
				data["screenshots"] = [x.public_url for x in package_screenshots]
				data["game_support"] = [
					{
						"supports": support.supports,
						"confidence": support.confidence,
						"game": support.game.as_short_dict(base_url),
					} for support in package.supported_games.all() if support.game.state == PackageState.APPROVED
				]

				prefix = f"backup/{package.author.username}/{package.name}"
				zipf.writestr(f"{prefix}/index.json", json.dumps(data, indent=4))

				releases = [release.as_dict() for release in
						package.releases.filter(PackageRelease.state == ReleaseState.APPROVED)]
				zipf.writestr(f"{prefix}/releases.json", json.dumps(releases, indent=4))

				content = json.dumps([screenshot_as_dict(x, package) for x in package_screenshots], indent=4)
				zipf.writestr(f"{prefix}/screenshots.json", content)

		# Uses a fixed name, as /uploads/backup-YYYY-MM-DD.zip is documented in help/backups
		copy_to_uploads(tmp_path, os.path.basename(tmp_path))
