# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import List, Dict, Optional, Tuple

import sqlalchemy

from app.models import PackageType, Package, PackageState, PackageGameSupport
from app.utils.models import post_bot_message


minetest_game_mods = {
	"beds", "boats", "bucket", "carts", "default", "dungeon_loot", "env_sounds", "fire", "flowers",
	"give_initial_stuff", "map", "player_api", "sethome", "spawn", "tnt", "walls", "wool",
	"binoculars", "bones", "butterflies", "creative", "doors", "dye", "farming", "fireflies", "game_commands",
	"keys", "mtg_craftguide", "screwdriver", "sfinv", "stairs", "vessels", "weather", "xpanes",
}


mtg_mod_blacklist = {
	"pacman", "tutorial", "runorfall", "realtest_mt5", "mevo", "xaenvironment",
	"survivethedays", "holidayhorrors",
}


class GSPackage:
	author: str
	name: str
	type: PackageType

	provides: set[str]
	depends: set[str]

	user_supported_games: set[str]
	user_unsupported_games: set[str]
	detected_supported_games: set[str]
	supports_all_games: bool

	detection_disabled: bool

	is_confirmed: bool
	errors: set[str]

	def __init__(self, author: str, name: str, type: PackageType, provides: set[str]):
		self.author = author
		self.name = name
		self.type = type
		self.provides = provides
		self.depends = set()
		self.user_supported_games = set()
		self.user_unsupported_games = set()
		self.detected_supported_games = set()
		self.supports_all_games = False
		self.detection_disabled = False
		self.is_confirmed = type == PackageType.GAME
		self.errors = set()

		# For dodgy games, discard MTG mods
		if self.type == PackageType.GAME and self.name in mtg_mod_blacklist:
			self.provides.difference_update(minetest_game_mods)

	@property
	def id_(self) -> str:
		return f"{self.author}/{self.name}"

	@property
	def supported_games(self) -> set[str]:
		ret = set()
		ret.update(self.user_supported_games)
		if not self.detection_disabled:
			ret.update(self.detected_supported_games)
		ret.difference_update(self.user_unsupported_games)
		return ret

	@property
	def unsupported_games(self) -> set[str]:
		return self.user_unsupported_games

	def add_error(self, error: str):
		return self.errors.add(error)


class GameSupport:
	packages: Dict[str, GSPackage]
	modified_packages: set[GSPackage]

	def __init__(self):
		self.packages = {}
		self.modified_packages = set()

	@property
	def all_confirmed(self):
		return all([x.is_confirmed for x in self.packages.values()])

	@property
	def has_errors(self):
		return any([len(x.errors) > 0 for x in self.packages.values()])

	@property
	def error_count(self):
		return sum([len(x.errors) for x in self.packages.values()])

	@property
	def all_errors(self) -> set[str]:
		errors = set()
		for package in self.packages.values():
			for err in package.errors:
				errors.add(package.id_ + ": " + err)
		return errors

	def add(self, package: GSPackage) -> GSPackage:
		self.packages[package.id_] = package
		return package

	def get(self, id_: str) -> Optional[GSPackage]:
		return self.packages.get(id_)

	def get_all_that_provide(self, modname: str) -> List[GSPackage]:
		return [package for package in self.packages.values() if modname in package.provides]

	def get_all_that_depend_on(self, modname: str) -> List[GSPackage]:
		return [package for package in self.packages.values() if modname in package.depends]

	def _get_supported_games_for_modname(self, depend: str, visited: list[str]):
		dep_supports_all = False
		for_dep = set()
		for provider in self.get_all_that_provide(depend):
			found_in = self._get_supported_games(provider, visited)
			if found_in is None:
				# Unsupported, keep going
				pass
			elif len(found_in) == 0:
				dep_supports_all = True
				break
			else:
				for_dep.update(found_in)

		return dep_supports_all, for_dep

	def _get_supported_games_for_deps(self, package: GSPackage, visited: list[str]) -> Optional[set[str]]:
		ret = set()

		for depend in package.depends:
			dep_supports_all, for_dep = self._get_supported_games_for_modname(depend, visited)

			if dep_supports_all:
				# Dep is game independent
				pass
			elif len(for_dep) == 0:
				package.add_error(f"Unable to fulfill dependency {depend}")
				return None
			elif len(ret) == 0:
				ret = for_dep
			else:
				ret.intersection_update(for_dep)
				if len(ret) == 0:
					package.add_error("Game support conflict, unable to install package on any games")
					return None

		return ret

	def _get_supported_games(self, package: GSPackage, visited: list[str]) -> Optional[set[str]]:
		if package.id_ in visited:
			return None

		if package.type == PackageType.GAME:
			return {package.name}
		elif package.is_confirmed:
			return package.supported_games

		visited = visited.copy()
		visited.append(package.id_)

		ret = self._get_supported_games_for_deps(package, visited)
		if ret is None:
			assert len(package.errors) > 0
			return None

		ret = ret.copy()
		ret.difference_update(package.user_unsupported_games)
		package.detected_supported_games = ret
		self.modified_packages.add(package)

		if len(ret) > 0:
			for supported in package.user_supported_games:
				if supported not in ret:
					package.add_error(f"`{supported}` is specified in supported_games but it is impossible to run {package.name} in that game. " +
							f"Its dependencies can only be fulfilled in {', '.join([f'`{x}`' for x in ret])}. " +
							"Check your hard dependencies.")

			if package.supports_all_games:
				package.add_error(
						"This package cannot support all games as some dependencies require specific game(s): " +
						", ".join([f'`{x}`' for x in ret]))

		package.is_confirmed = True
		return package.supported_games

	def on_update(self, package: GSPackage, old_provides: Optional[set[str]] = None):
		to_update = {package}
		checked = set()

		while len(to_update) > 0:
			current_package = to_update.pop()
			if current_package.id_ in self.packages and current_package.type != PackageType.GAME:
				self._get_supported_games(current_package, [])

			provides = current_package.provides
			if current_package == package and old_provides is not None:
				provides = provides.union(old_provides)

			for modname in provides:
				for depending_package in self.get_all_that_depend_on(modname):
					if depending_package not in checked:
						if depending_package.id_ in self.packages and depending_package.type != PackageType.GAME:
							depending_package.is_confirmed = False
							depending_package.detected_supported_games = []

						to_update.add(depending_package)
						checked.add(depending_package)

	def on_remove(self, package: GSPackage):
		del self.packages[package.id_]
		self.on_update(package)

	def on_first_run(self):
		for package in self.packages.values():
			if not package.is_confirmed:
				self.on_update(package)


def _convert_package(support: GameSupport, package: Package) -> GSPackage:
	# Unapproved packages shouldn't be considered to fulfill anything
	provides = set()
	if package.state == PackageState.APPROVED:
		provides = set([x.name for x in package.provides])

	gs_package = GSPackage(package.author.username, package.name, package.type, provides)
	gs_package.depends = set([x.meta_package.name for x in package.dependencies if not x.optional])
	gs_package.detection_disabled = not package.enable_game_support_detection
	gs_package.supports_all_games = package.supports_all_games

	existing_game_support = (package.supported_games
			.filter(PackageGameSupport.game.has(state=PackageState.APPROVED),
					PackageGameSupport.confidence > 5)
			.all())
	if not package.supports_all_games:
		gs_package.user_supported_games = [x.game.name for x in existing_game_support if x.supports]
	gs_package.user_unsupported_games = [x.game.name for x in existing_game_support if not x.supports]
	return support.add(gs_package)


def _create_instance(session: sqlalchemy.orm.Session) -> GameSupport:
	support = GameSupport()

	packages: List[Package] = (session.query(Package)
			.filter(Package.state == PackageState.APPROVED, Package.type.in_([PackageType.GAME, PackageType.MOD]))
			.all())

	for package in packages:
		_convert_package(support, package)

	return support


def _persist(session: sqlalchemy.orm.Session, support: GameSupport):
	for gs_package in support.packages.values():
		if len(gs_package.errors) != 0:
			msg = "\n".join([f"- {x}" for x in gs_package.errors])
			package = session.query(Package).filter(
					Package.author.has(username=gs_package.author),
					Package.name == gs_package.name).one()
			post_bot_message(package, "Error when checking game support", msg, session)

	for gs_package in support.modified_packages:
		if not gs_package.detection_disabled:
			package = session.query(Package).filter(
					Package.author.has(username=gs_package.author),
					Package.name == gs_package.name).one()

			# Clear existing
			session.query(PackageGameSupport) \
				.filter_by(package=package, confidence=1) \
				.delete()

			# Add new
			supported_games = gs_package.supported_games \
				.difference(gs_package.user_supported_games)
			for game_name in supported_games:
				game_id = session.query(Package.id) \
					.filter(Package.type == PackageType.GAME, Package.name == game_name, Package.state == PackageState.APPROVED) \
					.one()[0]

				new_support = PackageGameSupport()
				new_support.package = package
				new_support.game_id = game_id
				new_support.confidence = 1
				new_support.supports = True
				session.add(new_support)


def game_support_update(session: sqlalchemy.orm.Session, package: Package, old_provides: Optional[set[str]]) -> set[str]:
	support = _create_instance(session)
	gs_package = support.get(package.get_id())
	if gs_package is None:
		gs_package = _convert_package(support, package)
	support.on_update(gs_package, old_provides)
	_persist(session, support)
	return gs_package.errors


def game_support_update_all(session: sqlalchemy.orm.Session):
	support = _create_instance(session)
	support.on_first_run()
	_persist(session, support)


def game_support_remove(session: sqlalchemy.orm.Session, package: Package):
	support = _create_instance(session)
	gs_package = support.get(package.get_id())
	if gs_package is None:
		gs_package = _convert_package(support, package)
	support.on_remove(gs_package)
	_persist(session, support)


def game_support_set(session, package: Package, game_is_supported: Dict[int, bool], confidence: int):
	previous_supported: Dict[int, PackageGameSupport] = {}
	for support in package.supported_games.all():
		previous_supported[support.game.id] = support

	for game_id, supports in game_is_supported.items():
		game = session.query(Package).get(game_id)
		lookup = previous_supported.pop(game_id, None)
		if lookup is None:
			support = PackageGameSupport()
			support.package = package
			support.game = game
			support.confidence = confidence
			support.supports = supports
			session.add(support)
		elif lookup.confidence <= confidence:
			lookup.supports = supports
			lookup.confidence = confidence

	for game, support in previous_supported.items():
		if support.confidence == confidence:
			session.delete(support)
