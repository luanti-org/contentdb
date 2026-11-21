# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
migrations/versions/a9d3f1c7e5b2_.py restricts the resolution tags to texture packs, removing them from other packages.
The test database is already migrated, so this runs the migration's upgrade against test data with `op` replaced.
"""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

from app.models import db, AuditLogEntry, Package, PackageType, Tag, User
from ..factories import create_package, create_user

MIGRATION = Path(__file__).parents[4] / "migrations/versions/a9d3f1c7e5b2_.py"


def load_migration() -> ModuleType:
	spec = importlib.util.spec_from_file_location("tag_restriction_migration", MIGRATION)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def run_upgrade():
	migration = load_migration()
	setattr(migration, "op", SimpleNamespace(execute=db.session.execute))
	migration.upgrade()
	db.session.commit()
	db.session.expire_all()


def tag(name: str) -> Tag:
	result = Tag.query.filter_by(name=name).first()
	if result is None:
		result = Tag(name)
		result.name = name
		db.session.add(result)
	return result


def tag_names(name: str) -> list[str]:
	return sorted(x.name for x in Package.query.filter_by(name=name).one().tags)


def test_restricts_tags_and_removes_them_from_other_types(client):
	author = create_user("author")
	game = create_package("game", author, type=PackageType.GAME)
	game.title = "Some Game"
	game.tags.extend([tag("16px"), tag("128px"), tag("survival")])
	mod = create_package("mod", author)
	mod.tags.extend([tag("survival"), tag("16px")])
	txp = create_package("pack", author, type=PackageType.TXP)
	txp.tags.extend([tag("16px"), tag("survival")])
	db.session.commit()

	run_upgrade()

	assert Tag.query.filter_by(name="16px").one().package_types == [PackageType.TXP]
	assert Tag.query.filter_by(name="128px").one().package_types == [PackageType.TXP]
	# Tags that categories overlap are left alone for now
	assert Tag.query.filter_by(name="survival").one().package_types == []

	# Resolution tags are removed from other types, and other tags are kept
	assert tag_names("game") == ["survival"]
	assert tag_names("mod") == ["survival"]
	assert tag_names("pack") == ["16px", "survival"]

	# One audit log entry per changed package, by the system user
	entry = AuditLogEntry.query.filter_by(package=Package.query.filter_by(name="game").one()).one()
	assert entry.title == "Removed tags from Some Game: 128px, 16px"
	assert entry.url == "/packages/author/game/"
	assert entry.causer == User.query.filter_by(username="ContentDB").one()
	assert AuditLogEntry.query.filter(AuditLogEntry.title.like("Removed tags from %")).count() == 2

	# Running it again changes nothing
	run_upgrade()
	assert AuditLogEntry.query.filter(AuditLogEntry.title.like("Removed tags from %")).count() == 2
