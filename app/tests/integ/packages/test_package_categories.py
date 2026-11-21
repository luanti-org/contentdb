# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Category tags on games: chosen in the package form or the API, at most two, and needed before publishing.
"""

from app.models import db, Package, PackageState, PackageType, PackageAIDisclosure, Tag, TagKind, User, UserRank
from ..factories import create_user, create_package, create_release, create_screenshot, create_token, \
	login_as, client_request
from .test_package_lifecycle import package_form, edit_form


def get_package(name: str = "pkg") -> Package:
	db.session.expire_all()
	return Package.query.filter_by(name=name).one()


def tag_names(package: Package) -> list[str]:
	return sorted(x.name for x in package.tags)


def make_categories() -> list[Tag]:
	categories = []
	for title in ["Puzzle Game", "Racing", "Survival Sandbox"]:
		tag = Tag(title)
		tag.kind = TagKind.CATEGORY
		tag.package_types = [PackageType.GAME]
		db.session.add(tag)
		categories.append(tag)
	db.session.commit()
	return categories


def ids(*tags: Tag) -> list[str]:
	return [str(x.id) for x in tags]


def mapgen() -> Tag:
	return Tag.query.filter_by(name="mapgen").one()


def test_create_game_with_categories(client):
	puzzle, racing, _ = make_categories()
	login_as(client, create_user("owner"))

	rv = client_request(client, "POST", "/packages/new/", data=package_form(type="GAME",
			categories=ids(puzzle, racing), tags=ids(mapgen())))

	assert rv.status_code == 302
	assert tag_names(get_package()) == ["mapgen", "puzzle_game", "racing"]


def test_create_game_without_category(client):
	make_categories()
	login_as(client, create_user("owner"))

	rv = client_request(client, "POST", "/packages/new/", data=package_form(type="GAME"))

	assert rv.status_code == 302
	assert tag_names(get_package()) == []


def test_create_game_with_too_many_categories(client):
	categories = make_categories()
	login_as(client, create_user("owner"))

	rv = client_request(client, "POST", "/packages/new/", data=package_form(type="GAME", categories=ids(*categories)))

	assert rv.status_code == 200
	assert "Choose at most 2 categories" in rv.data.decode("utf-8")
	assert Package.query.count() == 0


def test_categories_ignored_for_other_types(client):
	puzzle, _, _ = make_categories()
	login_as(client, create_user("owner"))

	# For example, ticked before changing the type from game to mod
	rv = client_request(client, "POST", "/packages/new/", data=package_form(type="MOD", categories=ids(puzzle)))

	assert rv.status_code == 302
	assert tag_names(get_package()) == []


def test_category_not_accepted_as_feature_tag(client):
	puzzle, _, _ = make_categories()
	login_as(client, create_user("owner"))

	rv = client_request(client, "POST", "/packages/new/", data=package_form(type="GAME", tags=ids(puzzle)))

	assert rv.status_code == 200
	assert Package.query.count() == 0


def test_edit_form_shows_categories_separately(client):
	puzzle, _, _ = make_categories()
	owner = create_user("owner")
	package = create_package("pkg", owner, type=PackageType.GAME)
	package.tags.extend([puzzle, mapgen()])
	db.session.commit()
	login_as(client, owner)

	html = client_request(client, "GET", "/packages/owner/pkg/edit/").data.decode("utf-8")

	category_input = next(x for x in html.split("<input") if f'value="{puzzle.id}"' in x and 'name="categories"' in x)
	assert "checked" in category_input
	assert "<strong>Puzzle Game</strong>" in html
	tags_select = html[html.index('<select class="form-control" id="tags"'):]
	tags_select = tags_select[:tags_select.index("</select>")]
	assert "Mapgen" in tags_select
	assert "Puzzle Game" not in tags_select

	# Saving without changes keeps both
	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package,
			categories=ids(puzzle), tags=ids(mapgen())))
	assert rv.status_code == 302
	assert tag_names(get_package()) == ["mapgen", "puzzle_game"]


def test_edit_tag_restricted_to_other_type(client):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	tag = mapgen()
	tag.package_types = [PackageType.GAME]
	db.session.commit()
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, tags=ids(tag)))

	assert rv.status_code == 200
	assert "The tag Mapgen can&#39;t be used on this type of package" in rv.data.decode("utf-8")
	assert tag_names(get_package()) == []


def put_tags(client, package: Package, tags: list[str]):
	_, access_token = create_token(package.author, package)
	return client_request(client, "PUT", f"/api/packages/{package.author.username}/{package.name}/",
			headers={"Authorization": f"Bearer {access_token}"}, json={"tags": tags})


def test_api_sets_categories(client):
	make_categories()
	package = create_package("pkg", create_user("owner"), type=PackageType.GAME)

	rv = put_tags(client, package, ["puzzle_game", "mapgen"])

	assert rv.status_code == 200, rv.json
	assert tag_names(get_package()) == ["mapgen", "puzzle_game"]


def test_api_keeps_categories_when_none_given(client):
	puzzle, _, _ = make_categories()
	package = create_package("pkg", create_user("owner"), type=PackageType.GAME)
	package.tags.append(puzzle)
	db.session.commit()

	# For example, an older client or a .cdb.json file that doesn't know about categories
	rv = put_tags(client, package, ["mapgen"])

	assert rv.status_code == 200, rv.json
	assert tag_names(get_package()) == ["mapgen", "puzzle_game"]

	# Replaced when categories are given
	rv = put_tags(client, get_package(), ["racing"])
	assert rv.status_code == 200, rv.json
	assert tag_names(get_package()) == ["racing"]


def test_edit_form_can_remove_all_categories(client):
	puzzle, _, _ = make_categories()
	owner = create_user("owner")
	package = create_package("pkg", owner, state=PackageState.WIP, type=PackageType.GAME)
	package.tags.append(puzzle)
	db.session.commit()
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package))

	assert rv.status_code == 302
	assert tag_names(get_package()) == []


def test_published_game_cant_remove_all_categories(client):
	puzzle, racing, _ = make_categories()
	owner = create_user("owner")
	package = create_package("pkg", owner, type=PackageType.GAME)
	package.tags.append(puzzle)
	db.session.commit()
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, tags=ids(mapgen())))

	assert rv.status_code == 200
	assert "Published games need at least one category" in rv.data.decode("utf-8")
	assert tag_names(get_package()) == ["puzzle_game"]

	# Changing category is fine
	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, categories=ids(racing)))
	assert rv.status_code == 302
	assert tag_names(get_package()) == ["racing"]


def test_published_game_without_categories_can_be_edited(client):
	make_categories()
	owner = create_user("owner")
	package = create_package("pkg", owner, type=PackageType.GAME)
	login_as(client, owner)

	# Published before categories existed
	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data=edit_form(package, tags=ids(mapgen())))

	assert rv.status_code == 302
	assert tag_names(get_package()) == ["mapgen"]


def test_api_rejects_too_many_categories(client):
	make_categories()
	package = create_package("pkg", create_user("owner"), type=PackageType.GAME)

	rv = put_tags(client, package, ["puzzle_game", "racing", "survival_sandbox"])

	assert rv.status_code == 400
	assert rv.json["error"] == "Choose at most 2 categories"
	assert tag_names(get_package()) == []


def test_api_rejects_category_on_mod(client):
	make_categories()
	package = create_package("pkg", create_user("owner"))

	rv = put_tags(client, package, ["puzzle_game"])

	assert rv.status_code == 400
	assert rv.json["error"] == "The tag Puzzle Game can't be used on this type of package"
	assert tag_names(get_package()) == []


def test_api_tags_list_kind_and_types(client):
	puzzle, _, _ = make_categories()
	puzzle.icon = "fa-puzzle-piece"
	db.session.commit()

	tags = {x["name"]: x for x in client.get("/api/tags/").json}

	assert tags["puzzle_game"]["kind"] == "category"
	assert tags["puzzle_game"]["package_types"] == ["game"]
	assert tags["mapgen"]["kind"] == "feature"
	assert tags["mapgen"]["package_types"] == []
	assert tags["puzzle_game"]["icon"] == "fa-puzzle-piece"
	assert tags["mapgen"]["icon"] is None


def make_ready_game() -> Package:
	owner = create_user("owner")
	create_user("approver", UserRank.APPROVER)
	package = create_package("pkg", owner, state=PackageState.WIP, type=PackageType.GAME)
	create_release(package, "1.0")
	create_screenshot(package, approved=False)
	package.ai_disclosure = PackageAIDisclosure.NONE
	db.session.commit()
	return package


def test_game_needs_category_to_be_submitted(client, eager_tasks, http_stub):
	puzzle, _, _ = make_categories()
	package = make_ready_game()
	login_as(client, User.query.filter_by(username="owner").one())

	html = client_request(client, "GET", "/packages/owner/pkg/").data.decode("utf-8")
	assert "You need to choose at least one category in the edit package form." in html

	client_request(client, "POST", "/packages/owner/pkg/state/?state=ready_for_review")
	assert get_package().state == PackageState.WIP

	package = get_package()
	package.tags.append(puzzle)
	db.session.commit()

	client_request(client, "POST", "/packages/owner/pkg/state/?state=ready_for_review")
	assert get_package().state == PackageState.READY_FOR_REVIEW
