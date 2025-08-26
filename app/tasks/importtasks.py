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
import json
import os
import shutil
import sys
from json import JSONDecodeError
from zipfile import ZipFile, BadZipFile

import gitdb
from flask import url_for
from git import GitCommandError
from git_archive_all import GitArchiver
from kombu import uuid
from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert

from app.models import AuditSeverity, db, NotificationType, PackageRelease, MetaPackage, Dependency, PackageType, \
	LuantiRelease, Package, PackageState, PackageScreenshot, PackageUpdateTrigger, PackageUpdateConfig, \
	PackageGameSupport, PackageTranslation, Language
from app.tasks import celery, TaskError
from app.utils import random_string, post_bot_message, add_system_notification, add_system_audit_log, \
	get_games_from_list, add_audit_log
from app.utils.git import clone_repo, get_latest_tag, get_latest_commit, get_temp_dir, get_release_notes
from .luanticheck import build_tree, LuantiCheckError, ContentType, PackageTreeNode
from .webhooktasks import post_discord_webhook
from app import app
from app.logic.LogicError import LogicError
from app.logic.packages import do_edit_package, ALIASES
from app.logic.game_support import game_support_update, game_support_set, game_support_update_all, game_support_remove
from app.utils.image import get_image_size


@celery.task()
def get_meta(urlstr, author):
	with clone_repo(urlstr, recursive=True) as repo:
		try:
			tree = build_tree(repo.working_tree_dir, author=author, repo=urlstr)
		except LuantiCheckError as err:
			raise TaskError(str(err))

		result = {"name": tree.name, "type": tree.type.name}

		for key in ["title", "repo", "issueTracker", "forumId", "description", "short_description"]:
			result[key] = tree.get(key)

		result["forums"] = result.get("forumId")

		readme_path = tree.get_readme_path()
		if readme_path:
			with open(readme_path, "r") as f:
				result["long_description"] = f.read()

		try:
			with open(os.path.join(tree.baseDir, ".cdb.json"), "r") as f:
				data = json.loads(f.read())
				for key, value in data.items():
					result[key] = value
		except JSONDecodeError as e:
			raise TaskError("Whilst reading .cdb.json: " + str(e))
		except IOError:
			pass

		for alias, to in ALIASES.items():
			if alias in result:
				result[to] = result[alias]

		for key, value in result.items():
			if isinstance(value, set):
				result[key] = list(value)

		return result


@celery.task()
def update_all_game_support():
	game_support_update_all(db.session)
	db.session.commit()


@celery.task()
def update_package_game_support(package_id: int):
	package = Package.query.get(package_id)
	game_support_update(db.session, package, None)
	db.session.commit()


@celery.task()
def remove_package_game_support(package_id: int):
	package = Package.query.get(package_id)
	game_support_remove(db.session, package)
	db.session.commit()


def post_release_check_update(self, release: PackageRelease, path):
	try:
		tree: PackageTreeNode = build_tree(path, expected_type=ContentType[release.package.type.name],
				author=release.package.author.username, name=release.package.name)

		if tree.name is not None and release.package.name != tree.name and tree.type == ContentType.MOD:
			raise LuantiCheckError(f"Expected {tree.relative} to have technical name {release.package.name}, instead has name {tree.name}")

		cache = {}
		def get_meta_packages(names):
			return [ MetaPackage.GetOrCreate(x, cache) for x in names ]

		provides = tree.get_mod_names()

		package = release.package
		if not package.approved:
			tree.check_for_legacy_files()

		old_provided_names = set([x.name for x in package.provides])
		package.provides.clear()

		# If new mods were added, add to audit log
		if package.state == PackageState.APPROVED:
			new_provides = []
			for modname in provides:
				if modname not in old_provided_names:
					new_provides.append(modname)

			if len(new_provides) > 0:
				msg = "Added mods: " + (", ".join(new_provides))
				add_audit_log(AuditSeverity.NORMAL, package.author, msg + " (Post release hook)", release.get_edit_url(), package)

				# Do any of these new mods exist elsewhere?
				new_names = get_meta_packages(new_provides)
				if any(map(lambda x: x.packages.filter(Package.state == PackageState.APPROVED).count() > 0, new_names)):
					discord_msg = (msg + " " + package.get_url("packages.similar", absolute=True) +
						"#" + new_provides[0] +
						"\nSome of these mods exist elsewhere, possible RTaN issue")
					post_discord_webhook.delay(package.author.display_name, discord_msg, True,
						package.title, package.short_desc, package.get_thumb_url(2, True, "png"))

		package.provides.extend(get_meta_packages(tree.get_mod_names()))

		# Delete all mod name dependencies
		package.dependencies.filter(Dependency.meta_package != None).delete()

		# Get raw dependencies
		depends = tree.fold("meta", "depends")
		optional_depends = tree.fold("meta", "optional_depends")

		# Filter out provides
		for mod in provides:
			depends.discard(mod)
			optional_depends.discard(mod)

		# Raise error on unresolved game dependencies
		if package.type == PackageType.GAME and len(depends) > 0:
			deps = ", ".join(depends)
			raise LuantiCheckError("Game has unresolved hard dependencies: " + deps)

		if package.state != PackageState.APPROVED and tree.find_license_file() is None:
			raise LuantiCheckError(
				"You need to add a LICENSE.txt/.md or COPYING file to your package. See the 'Copyright Guide' for more info")

		# Add dependencies
		for meta in get_meta_packages(depends):
			db.session.add(Dependency(package, meta=meta, optional=False))

		for meta in get_meta_packages(optional_depends):
			db.session.add(Dependency(package, meta=meta, optional=True))

		# Read translations
		update_translations(package, tree)

		# Update min/max
		if tree.meta.get("min_minetest_version"):
			release.min_rel = LuantiRelease.get(tree.meta["min_minetest_version"], None)

		if tree.meta.get("max_minetest_version"):
			release.max_rel = LuantiRelease.get(tree.meta["max_minetest_version"], None)

		try:
			with open(os.path.join(tree.baseDir, ".cdb.json"), "r") as f:
				data = json.loads(f.read())
				do_edit_package(package.author, package, False, False, data, "Post release hook")
		except LogicError as e:
			raise TaskError("Whilst applying .cdb.json: " + e.message)
		except JSONDecodeError as e:
			raise TaskError("Whilst reading .cdb.json: " + str(e))
		except IOError:
			pass

		# Build release notes from git log
		if release.commit_hash and release.release_notes is None:
			previous_release = package.releases.filter(PackageRelease.id != release.id).first()
			if previous_release and previous_release.commit_hash:
				release.release_notes = get_release_notes(package.repo, previous_release.commit_hash, release.commit_hash)

		# Update game support
		if package.type == PackageType.MOD or package.type == PackageType.TXP:
			game_is_supported = {}
			if "supported_games" in tree.meta:
				for game in get_games_from_list(db.session, tree.meta["supported_games"]):
					game_is_supported[game.id] = True

				has_star = any(map(lambda x: x.strip() == "*", tree.meta["supported_games"]))
				if has_star:
					if package.type == PackageType.TXP or \
						package.supported_games.filter(and_(
							PackageGameSupport.confidence == 1, PackageGameSupport.supports == True)).count() > 0:
						raise TaskError("The package depends on a game-specific mod, and so cannot support all games.")

					package.supports_all_games = True
			if "unsupported_games" in tree.meta:
				for game in get_games_from_list(db.session, tree.meta["unsupported_games"]):
					game_is_supported[game.id] = False

			game_support_set(db.session, package, game_is_supported, 10)
			if package.type == PackageType.MOD:
				errors = game_support_update(db.session, package, old_provided_names)
				if len(errors) != 0:
					raise TaskError("Error validating game support:\n\n" + "\n".join([f"- {x}" for x in errors]))

		return tree

	except (LuantiCheckError, TaskError, LogicError) as err:
		db.session.rollback()

		error_message = err.value if hasattr(err, "value") else str(err)

		task_url = url_for('tasks.check', id=self.request.id)
		msg = f"{error_message}\n\n[View Release]({release.get_edit_url()}) | [View Task]({task_url})"
		post_bot_message(release.package, f"Release {release.title} validation failed", msg)

		if "Fails validation" not in release.title:
			release.title += " (Fails validation)"

		release.task_id = self.request.id
		release.approved = False
		db.session.commit()

		raise TaskError(error_message)


def update_translations(package: Package, tree: PackageTreeNode):
	allowed_languages = set([x[0] for x in db.session.query(Language.id).all()])
	allowed_languages.discard("en")
	conn = db.session.connection()
	for language in tree.get_supported_languages():
		if language not in allowed_languages:
			continue

		values = {
			"package_id": package.id,
			"language_id": language,
		}
		stmt = insert(PackageTranslation).values(**values)
		stmt = stmt.on_conflict_do_nothing(
			index_elements=[PackageTranslation.package_id, PackageTranslation.language_id],
		)
		conn.execute(stmt)

	raw_translations = tree.get_translations(tree.get("textdomain", tree.name), allowed_languages=allowed_languages)
	for raw_translation in raw_translations:
		to_update = {
			"title": raw_translation.entries.get(tree.get("title", package.title)),
			"short_desc": raw_translation.entries.get(tree.get("description", package.short_desc)),
		}

		PackageTranslation.query \
			.filter_by(package_id=package.id, language_id=raw_translation.language) \
			.update(to_update)


def _check_zip_file(temp_dir: str, zf: ZipFile) -> bool:
	# No more than 300MB
	total_size = sum(e.file_size for e in zf.infolist())
	if total_size > 300 * 1024 * 1024:
		print(f"zip file is too large: {total_size} bytes", file=sys.stderr)
		return False

	# Check paths
	for member in zf.infolist():
		# We've had cases of newlines in filenames
		if "\n" in member.filename:
			print("zip file member contains invalid characters", file=sys.stderr)
			return False

		file_path = os.path.realpath(os.path.join(temp_dir, member.filename))
		if not file_path.startswith(os.path.realpath(temp_dir)):
			print(f"zip file contains path out-of-bounds: {file_path}", file=sys.stderr)
			return False

	return True


def _safe_extract_zip(temp_dir: str, archive_path: str) -> bool:
	try:
		with ZipFile(archive_path, 'r') as zf:
			if not _check_zip_file(temp_dir, zf):
				return False

			# Extract all
			for member in zf.infolist():
				zf.extract(member, temp_dir)
	except BadZipFile as e:
		raise TaskError(str(e))

	return True


@celery.task(bind=True)
def check_zip_release(self, id, path):
	release = PackageRelease.query.get(id)
	if release is None:
		raise TaskError("No such release!")
	elif release.package is None:
		raise TaskError("No package attached to release")

	with get_temp_dir() as temp:
		if not _safe_extract_zip(temp, path):
			release.approved = False
			db.session.commit()
			raise Exception(f"Unsafe zip file at {path}")

		post_release_check_update(self, release, temp)

		release.task_id = None
		release.calculate_file_size_bytes()
		release.approve(release.package.author)
		db.session.commit()


@celery.task()
def check_all_zip_files():
	result = []

	releases = PackageRelease.query.all()
	for release in releases:
		with ZipFile(release.file_path, 'r') as zf:
			if not _check_zip_file("/tmp/example", zf):
				print(f"Unsafe zip file for {release.package.get_id()} at {release.file_path}", file=sys.stderr)
				result.append({
					"package": release.package.get_id(),
					"file": release.file_path,
				})

	return json.dumps(result)


@celery.task(bind=True)
def import_languages(self, id, path):
	release = PackageRelease.query.get(id)
	if release is None:
		raise TaskError("No such release!")
	elif release.package is None:
		raise TaskError("No package attached to release")

	with get_temp_dir() as temp:
		if not _safe_extract_zip(temp, path):
			raise Exception(f"Unsafe zip file at {path}")

		try:
			tree: PackageTreeNode = build_tree(temp,
					expected_type=ContentType[release.package.type.name],
					author=release.package.author.username,
					name=release.package.name,
					strict=False)
			update_translations(release.package, tree)
			db.session.commit()
		except (LuantiCheckError, TaskError, LogicError) as err:
			db.session.rollback()

			task_url = url_for('tasks.check', id=self.request.id)
			msg = f"{err}\n\n[View Release]({release.get_edit_url()}) | [View Task]({task_url})"
			post_bot_message(release.package, f"Release {release.title} validation failed", msg)
			db.session.commit()

			raise TaskError(str(err))


@celery.task(bind=True)
def make_vcs_release(self, id, branch):
	release = PackageRelease.query.get(id)
	if release is None:
		raise TaskError("No such release!")
	elif release.package is None:
		raise TaskError("No package attached to release")

	with clone_repo(release.package.repo, ref=branch, recursive=True) as repo:
		release.commit_hash = repo.head.object.hexsha
		post_release_check_update(self, release, repo.working_tree_dir)

		filename = random_string(10) + ".zip"
		dest_path = os.path.join(app.config["UPLOAD_DIR"], filename)

		assert not os.path.isfile(dest_path)
		archiver = GitArchiver(prefix=release.package.name, force_sub=True, main_repo_abspath=repo.working_tree_dir)
		archiver.create(dest_path)
		assert os.path.isfile(dest_path)

		file_stats = os.stat(dest_path)
		if file_stats.st_size / (1024 * 1024) > 100:
			os.remove(dest_path)
			raise TaskError("The .zip file created from Git is too large - needs to be less than 100MB")

		release.url         = "/uploads/" + filename
		release.task_id     = None
		release.calculate_file_size_bytes()
		release.approve(release.package.author)
		db.session.commit()

		return release.url


@celery.task()
def import_repo_screenshot(id):
	package = Package.query.get(id)
	if package is None or package.state == PackageState.DELETED:
		raise Exception("Unexpected none package")

	try:
		with clone_repo(package.repo) as repo:
			for ext in ["png", "jpg", "jpeg"]:
				sourcePath = repo.working_tree_dir + "/screenshot." + ext
				if os.path.isfile(sourcePath):
					filename = random_string(10) + "." + ext
					destPath = os.path.join(app.config["UPLOAD_DIR"], filename)
					shutil.copyfile(sourcePath, destPath)

					ss = PackageScreenshot()
					ss.approved = True
					ss.package = package
					ss.title   = "screenshot.png"
					ss.url	 = "/uploads/" + filename
					ss.width, ss.height = get_image_size(destPath)
					if ss.is_too_small():
						return None

					db.session.add(ss)
					db.session.commit()

					return "/uploads/" + filename

	except TaskError as e:
		# ignore download errors
		print(e)
		pass

	print("screenshot.png does not exist")
	return None


def check_update_config_impl(package):
	config = package.update_config

	if config.trigger == PackageUpdateTrigger.COMMIT:
		tag = None
		commit = get_latest_commit(package.repo, package.update_config.ref)
		release_notes = None
	elif config.trigger == PackageUpdateTrigger.TAG:
		tag, commit, release_notes = get_latest_tag(package.repo)
	else:
		raise TaskError("Unknown update trigger")

	if commit is None:
		return

	if config.last_commit == commit:
		if tag and config.last_tag != tag:
			config.last_tag = tag
		return

	if not config.last_commit:
		config.last_commit = commit
		config.last_tag = tag
		return

	if package.releases.filter_by(commit_hash=commit).count() > 0:
		return

	if config.make_release:
		rel = PackageRelease()
		rel.package = package
		rel.name = tag if tag else datetime.datetime.utcnow().strftime("%Y-%m-%d")
		rel.title = rel.name
		rel.release_notes = release_notes
		rel.url = ""
		rel.task_id = uuid()
		db.session.add(rel)

		msg = "Created release {} (Git Update Detection)".format(rel.title)
		add_system_audit_log(AuditSeverity.NORMAL, msg, package.get_url("packages.view"), package)

		make_vcs_release.apply_async((rel.id, commit), task_id=rel.task_id)

	elif config.outdated_at is None:
		config.set_outdated()

		if config.trigger == PackageUpdateTrigger.COMMIT:
			msg_last = ""
			if config.last_commit:
				msg_last = " The last commit was {}".format(config.last_commit[0:5])

			msg = "New commit {} found on the Git repo, is the package outdated?{}" \
				.format(commit[0:5], msg_last)
		else:
			msg_last = ""
			if config.last_tag:
				msg_last = " The last tag was {}".format(config.last_tag)

			msg = "New tag {} found on the Git repo.{}" \
				.format(tag, msg_last)

		for user in package.maintainers:
			add_system_notification(user, NotificationType.BOT,
					msg, url_for("todo.view_user", username=user.username, _external=False), package)

	config.last_commit = commit
	config.last_tag = tag


def check_update_config(self, package_id):
	package: Package = Package.query.get(package_id)
	if package is None:
		raise TaskError("No such package!")
	elif package.update_config is None:
		raise TaskError("No update config attached to package")

	err = None
	try:
		check_update_config_impl(package)

		package.update_config.last_checked_at = datetime.datetime.now()
		db.session.commit()
	except GitCommandError as e:
		# This is needed to stop the backtrace being weird
		err = e.stderr
	except gitdb.exc.BadName as e:
		err = "Unable to find the reference " + (package.update_config.ref or "?") + "\n" + e.stderr
	except TaskError as e:
		err = e.value

	if err:
		err = err.replace("stderr: ", "") \
			.replace("Cloning into '/tmp/", "Cloning into '") \
			.strip()

		msg = "Error: {}.\n\n[Change update configuration]({}) | [View task]({})" \
			.format(err, package.get_url("packages.update_config"), url_for("tasks.check", id=self.request.id))

		post_bot_message(package, "Failed to check git repository", msg)

		db.session.commit()
		return


@celery.task(bind=True, rate_limit="60/m")
def check_update_config_default(self, package_id):
	check_update_config(self, package_id)


@celery.task(bind=True, rate_limit="400/h")
def check_update_config_codeberg(self, package_id):
	check_update_config(self, package_id)



@celery.task
def check_for_updates():
	for update_config in PackageUpdateConfig.query.all():
		update_config: PackageUpdateConfig

		if not update_config.package.approved:
			continue

		if update_config.package.repo is None:
			db.session.delete(update_config)
			continue

		if "codeberg.org" in update_config.package.repo:
			check_update_config_codeberg.delay(update_config.package_id)
		else:
			check_update_config_default.delay(update_config.package_id)

	db.session.commit()
