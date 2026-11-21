# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import importlib.util
from pathlib import Path
from types import ModuleType

from app.blueprints.homepage.widgets.categories import DEFAULT_CATEGORY_ICON
from app.utils.icons import is_icon

ROOT = Path(__file__).parents[4]


def load_migration(revision: str) -> ModuleType:
	spec = importlib.util.spec_from_file_location(f"migration_{revision}", ROOT / f"migrations/versions/{revision}_.py")
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def test_migration_gives_every_category_an_icon():
	categories = [name for name, _, _ in load_migration("c4f1a9e2d7b3").CATEGORIES]
	icons = load_migration("f2b6d8e4a1c9").CATEGORY_ICONS
	assert set(icons.keys()) == set(categories)
	for icon in [*icons.values(), DEFAULT_CATEGORY_ICON]:
		assert is_icon(icon), icon


def test_is_icon():
	assert is_icon("fa-dragon")
	# Font Awesome 6 names don't exist in the bundled version 5
	assert not is_icon("fa-screwdriver-wrench")
	# Brand icons need "fab", not "fas"
	assert not is_icon("fa-github")
	assert not is_icon("dragon")
	assert not is_icon("fa-dragon extra-class")
	assert not is_icon("fa-dragon\" onmouseover=\"")
