# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from unittest import mock

import pytest

from app.domain.DomainError import DomainError
from app.domain.packages import MAX_CATEGORIES, validate_package_tags
from app.models import Package, PackageState, PackageType, Tag, TagKind


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


def make_category(title: str) -> Tag:
	tag = Tag(title)
	tag.kind = TagKind.CATEGORY
	tag.package_types = [PackageType.GAME]
	return tag


def make_package(type_: PackageType, tags: list[Tag], state: PackageState = PackageState.WIP) -> Package:
	package = Package()
	package.type = type_
	package.state = state
	package.tags = tags
	return package


@mock.patch("app.models.packages.pgettext", side_effect=lambda context, text: text)
def test_validate_package_tags(_pgettext):
	pvp = Tag("PvP")
	categories = [make_category(x) for x in ["Puzzle Game", "Survival Sandbox", "Racing"]]

	# Games may have no categories yet, so drafts can be saved
	validate_package_tags(make_package(PackageType.GAME, [pvp]), False)
	validate_package_tags(make_package(PackageType.GAME, [pvp, *categories[:MAX_CATEGORIES]]), False)

	with pytest.raises(DomainError) as e:
		validate_package_tags(make_package(PackageType.GAME, categories), False)
	assert str(e.value.message) == "Choose at most 2 categories"

	with pytest.raises(DomainError) as e:
		validate_package_tags(make_package(PackageType.MOD, [pvp, categories[0]]), False)
	assert str(e.value.message) == "The tag Puzzle Game can't be used on this type of package"
	# A plain string, so templates escape the editor-written title. LazyStrings are treated as safe HTML
	assert not hasattr(e.value.message, "__html__")


def test_published_game_must_keep_a_category():
	category = make_category("Puzzle Game")
	pvp = Tag("PvP")

	# Drafts can remove all their categories
	validate_package_tags(make_package(PackageType.GAME, [pvp]), True)

	with pytest.raises(DomainError) as e:
		validate_package_tags(make_package(PackageType.GAME, [pvp], PackageState.APPROVED), True)
	assert str(e.value.message) == "Published games need at least one category"

	validate_package_tags(make_package(PackageType.GAME, [category], PackageState.APPROVED), True)

	# Published before categories existed
	validate_package_tags(make_package(PackageType.GAME, [pvp], PackageState.APPROVED), False)


@mock.patch("app.models.packages.pgettext", side_effect=lambda context, text: text)
def test_checkbox_label_bolds_title(_pgettext):
	from app.blueprints.packages.packages import make_checkbox_label

	tag = make_category("Puzzle")
	assert make_checkbox_label(tag) == "<strong>Puzzle</strong>"

	tag.description = "Think <hard> & solve"
	assert make_checkbox_label(tag) == \
		'<strong>Puzzle</strong>: <span class="text-muted">Think &lt;hard&gt; &amp; solve</span>'


def test_strict_query_select_multiple_rejects_unknown_ids():
	from werkzeug.datastructures import MultiDict
	from wtforms import Form
	from app.blueprints.packages.packages import StrictQuerySelectMultipleField

	tags = [Tag("PvP"), Tag("Mobs")]
	for i, tag in enumerate(tags):
		tag.id = i + 1

	class TagsForm(Form):
		tags = StrictQuerySelectMultipleField(query_factory=lambda: tags, get_pk=lambda a: a.id)

	assert TagsForm(MultiDict([("tags", "1"), ("tags", "2")])).validate()
	assert not TagsForm(MultiDict([("tags", "1"), ("tags", "3")])).validate()
