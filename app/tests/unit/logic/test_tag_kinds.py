# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest

from app.models import PackageType, Tag, TagKind


def make_tag(package_types: list[PackageType] | None) -> Tag:
	tag = Tag("Example")
	tag.package_types = package_types
	return tag


def test_tag_applies_to_all_types_when_none_are_set():
	package_types: list[PackageType] | None
	for package_types in [None, []]:
		tag = make_tag(package_types)
		assert all(tag.applies_to(x) for x in PackageType)


def test_tag_applies_to_listed_types_only():
	tag = make_tag([PackageType.GAME, PackageType.TXP])
	assert tag.applies_to(PackageType.GAME)
	assert tag.applies_to(PackageType.TXP)
	assert not tag.applies_to(PackageType.MOD)


def test_tag_kind_coerce():
	assert TagKind.coerce("CATEGORY") == TagKind.CATEGORY
	assert TagKind.coerce(TagKind.FEATURE) == TagKind.FEATURE
	assert [name for name, _ in TagKind.choices()] == ["FEATURE", "CATEGORY"]

	# A ValueError, so WTForms shows it as a validation error rather than crashing
	with pytest.raises(ValueError):
		TagKind.coerce("Category")
