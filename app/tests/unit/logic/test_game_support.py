# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import List

from app.logic.game_support import GSPackage, GameSupport
from app.models import PackageType


def make_mod(name: str, provides: List[str], deps: List[str]) -> GSPackage:
	ret = GSPackage("author", name, PackageType.MOD, set(provides))
	ret.depends.update(deps)
	return ret


def make_game(name: str, provides: List[str]) -> GSPackage:
	return GSPackage("author", name, PackageType.GAME, set(provides))


def test_game_supports_itself():
	"""
	Games obviously support themselves
	"""
	support = GameSupport()
	game = support.add(make_game("game1", ["default"]))

	assert not support.has_errors
	assert game.is_confirmed
	assert len(game.detected_supported_games) == 0

	support.on_update(game)

	assert not support.has_errors
	assert game.is_confirmed
	assert len(game.detected_supported_games) == 0


def test_no_deps():
	"""
	Test a mod with no dependencies supports all games
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	mod1 = support.add(make_mod("mod1", ["mod1"], []))
	support.on_update(mod1)

	assert not support.has_errors
	assert mod1.is_confirmed
	assert len(mod1.detected_supported_games) == 0


def test_direct_game_dep():
	"""
	Test that depending on a mod in a game works
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	mod1 = support.add(make_mod("mod1", ["mod1"], ["default"]))
	support.on_update(mod1)

	assert not support.has_errors
	assert mod1.is_confirmed
	assert mod1.detected_supported_games == {"game1"}


def test_indirect_game_dep():
	"""
	Test that depending on a mod that depends on a game works
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	mod1 = support.add(make_mod("mod1", ["mod1"], ["default"]))
	mod2 = support.add(make_mod("mod2", ["mod2"], ["mod1"]))
	support.on_update(mod2)

	assert not support.has_errors
	assert mod1.is_confirmed
	assert mod1.detected_supported_games == {"game1"}
	assert mod2.is_confirmed
	assert mod2.detected_supported_games == {"game1"}


def test_multiple_game_dep():
	"""
	Test with multiple games, with dependencies in games and as standalone mods
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["core", "mod_b"]))
	lib = support.add(make_mod("lib", ["lib"], []))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b", "lib"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1", "game2"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0


def test_dependency_supports_all():
	"""
	Test with dependencies that support all games
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	mod1 = support.add(make_mod("mod1", ["mod1"], ["default"]))
	lib = support.add(make_mod("lib", ["lib"], []))
	mod2 = support.add(make_mod("mod2", ["mod2"], ["mod1", "lib"]))
	support.on_update(mod2)

	assert not support.has_errors

	assert mod1.is_confirmed
	assert mod1.detected_supported_games == {"game1"}

	assert mod2.is_confirmed
	assert mod2.detected_supported_games == {"game1"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0


def test_dependency_supports_all2():
	"""
	Test with dependencies that support all games, but are also in games
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default", "lib"]))
	lib = support.add(make_mod("lib", ["lib"], []))
	mod1 = support.add(make_mod("mod1", ["mod1"], ["lib"]))
	support.on_update(mod1)

	assert not support.has_errors

	assert mod1.is_confirmed
	assert len(mod1.detected_supported_games) == 0

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0


def test_dependency_game_conflict():
	"""
	Test situation where a mod is not installable in any games
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default", "mod_b"]))
	support.add(make_game("game2", ["default", "mod_c"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b", "mod_c"]))
	support.on_update(modA)

	assert not modA.is_confirmed
	assert len(modA.detected_supported_games) == 0

	assert support.all_errors == {
		"author/mod_a: Game support conflict, unable to install package on any games"
	}


def test_missing_hard_dep():
	"""
	Test missing hard dependency
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["nonexist"]))
	support.on_update(modA)

	assert not modA.is_confirmed
	assert len(modA.detected_supported_games) == 0
	assert support.all_errors == {
		"author/mod_a: Unable to fulfill dependency nonexist"
	}


def test_cycle():
	"""
	Test for dependency cycles
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_mod("mod_b", ["mod_b"], ["mod_a"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	support.on_update(modA)

	assert support.all_errors == {
		"author/mod_b: Unable to fulfill dependency mod_a",
		"author/mod_a: Unable to fulfill dependency mod_b"
	}


def test_cycle_fails_safely():
	"""
	A dependency cycle shouldn't completely break the graph if a mod is
	available elsewhere
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default", "mod_d"]))
	modC = support.add(make_mod("mod_c", ["mod_c"], ["mod_b"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["mod_c"]))
	support.add(make_mod("mod_d", ["mod_d"], ["mod_b"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_d"]))
	support.on_update(modA)

	assert not modC.is_confirmed
	assert not modB.is_confirmed
	assert modA.is_confirmed
	assert len(modA.errors) == 0
	assert modA.detected_supported_games == {"game1"}

	assert support.all_errors == {
		"author/mod_b: Unable to fulfill dependency mod_c",
		"author/mod_d: Unable to fulfill dependency mod_b",
		"author/mod_c: Unable to fulfill dependency mod_b",
	}


def test_update():
	"""
	Test updating a mod will update mods that depend on it
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	game2 = support.add(make_game("game2", ["core"]))
	lib = support.add(make_mod("lib", ["lib"], []))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b", "lib"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0

	game2.provides.add("mod_b")
	support.on_update(game2)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1", "game2"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0


def test_update_new_mod():
	"""
	Test that adding a mod will update mods that depend on the modname
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["core", "mod_b"]))
	lib = support.add(make_mod("lib", ["lib"], []))
	modC = support.add(make_mod("mod_c", ["mod_c"], ["mod_b"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b", "mod_c", "lib"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game2"}

	assert modC.is_confirmed
	assert modC.detected_supported_games == {"game2"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0

	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	support.on_update(modB)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1", "game2"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}

	assert modC.is_confirmed
	assert modC.detected_supported_games == {"game1", "game2"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0


def test_update_remove_mod():
	"""
	Test that removing a mod from provides will update mods that depended on the modname
	"""
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	game2 = support.add(make_game("game2", ["core", "mod_b"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	lib = support.add(make_mod("lib", ["lib"], []))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b", "lib"]))
	support.on_first_run()

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1", "game2"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0

	old_provides = game2.provides.copy()
	game2.provides.remove("mod_b")
	support.on_update(game2, old_provides)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}

	assert lib.is_confirmed
	assert len(lib.detected_supported_games) == 0


def test_update_cycle():
	"""
	Test that updating a package with a cycle depending on it doesn't break
	"""
	support = GameSupport()
	game1 = support.add(make_game("game1", ["default"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}

	support.add(make_mod("mod_c", ["mod_c"], ["mod_a"]))
	modA.depends.add("mod_c")
	support.on_update(game1)

	assert support.all_errors == {
		"author/mod_a: Unable to fulfill dependency mod_c",
		"author/mod_c: Unable to fulfill dependency mod_a"
	}


def test_remove():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["core", "mod_b"]))
	support.add(make_mod("lib", ["lib"], []))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b", "lib"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert len(modA.detected_supported_games) == 2
	assert "game1" in modA.detected_supported_games
	assert "game2" in modA.detected_supported_games

	assert modB.is_confirmed
	assert len(modB.detected_supported_games) == 1
	assert "game1" in modB.detected_supported_games

	support.on_remove(modB)

	assert not support.has_errors

	assert modA.is_confirmed
	assert len(modA.detected_supported_games) == 1
	assert "game2" in modA.detected_supported_games


def test_propagates_user_unsupported_games():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["default"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modB.user_supported_games.add("game1")
	modB.user_unsupported_games.add("game2")
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1"}
	assert modA.supported_games == {"game1"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1"}
	assert modB.supported_games == {"game1"}


def test_propagates_user_supported_games():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["default"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], []))
	modB.user_supported_games.add("game1")
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1"}

	assert modB.is_confirmed
	assert len(modB.detected_supported_games) == 0


def test_validate_inconsistent_user_supported_game():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["core"]))
	support.add(make_mod("mod_b", ["mod_b"], ["core"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	modA.user_supported_games.add("game1")
	support.on_update(modA)

	assert support.all_errors == {
		"author/mod_a: `game1` is specified in supported_games but it is impossible to run mod_a in that game. "
			"Its dependencies can only be fulfilled in `game2`. "
			"Check your hard dependencies.",
	}


def test_validate_inconsistent_supports_all():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["core"]))
	support.add(make_mod("mod_b", ["mod_b"], ["core"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	modA.supports_all_games = True
	support.on_update(modA)

	assert support.all_errors == {
		"author/mod_a: This package cannot support all games as some dependencies require specific game(s): `game2`",
	}


def test_enable_detection():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["default"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modB.user_supported_games.add("game1")
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1", "game2"}
	assert modA.supported_games == {"game1", "game2"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1", "game2"}
	assert modB.supported_games == {"game1", "game2"}


def test_disable_detection():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["default"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modB.user_supported_games.add("game1")
	modB.detection_disabled = True
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b"]))
	support.on_update(modA)

	assert not support.has_errors

	assert modA.is_confirmed
	assert modA.detected_supported_games == {"game1"}
	assert modA.supported_games == {"game1"}

	assert modB.is_confirmed
	assert modB.detected_supported_games == {"game1", "game2"}
	assert modB.supported_games == {"game1"}


def test_first_run():
	support = GameSupport()
	support.add(make_game("game1", ["default"]))
	support.add(make_game("game2", ["core", "mod_b"]))
	lib = support.add(make_mod("lib", ["lib"], []))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["default"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["mod_b", "lib"]))
	modF = support.add(make_mod("mod_f", ["mod_f"], []))

	assert not support.all_confirmed
	support.on_first_run()
	assert support.all_confirmed

	assert not support.has_errors
	assert modA.detected_supported_games == {"game1", "game2"}
	assert modB.detected_supported_games == {"game1"}
	assert len(lib.detected_supported_games) == 0
	assert len(modF.detected_supported_games) == 0


def test_ignores_mtg_in_violating_games():
	support = GameSupport()
	support.add(make_game("minetest_game", ["default"]))
	support.add(make_game("tutorial", ["default", "tutorial"]))
	modA = support.add(make_mod("mod_a", ["mod_a"], ["default"]))
	modB = support.add(make_mod("mod_b", ["mod_b"], ["tutorial"]))
	support.on_first_run()

	assert not support.has_errors
	assert modA.detected_supported_games == {"minetest_game"}
	assert modB.detected_supported_games == {"tutorial"}
