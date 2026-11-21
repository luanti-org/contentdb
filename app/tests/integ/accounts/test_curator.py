# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
The Curator rank: edits tag definitions, any package's tags and categories (but nothing else about a package),
dashboards, and ContentDB's collections.
"""

import pytest

from app.domain.DomainError import DomainError
from app.domain.packages import do_edit_package
from app.models import db, AuditLogEntry, Collection, Package, PackageType, Tag, TagKind, User, UserRank
from ..factories import create_collection, create_package, create_user, login_as, client_request


def get_package(name: str = "pkg") -> Package:
	db.session.expire_all()
	return Package.query.filter_by(name=name).one()


def make_category(title: str) -> Tag:
	tag = Tag(title)
	tag.kind = TagKind.CATEGORY
	tag.package_types = [PackageType.GAME]
	db.session.add(tag)
	db.session.commit()
	return tag


def tag_names(package: Package) -> list[str]:
	return sorted(x.name for x in package.tags)


def test_curator_edits_package_tags_and_categories(client):
	puzzle = make_category("Puzzle Game")
	make_category("Racing")
	mapgen = Tag.query.filter_by(name="mapgen").one()
	create_package("pkg", create_user("owner"), type=PackageType.GAME)
	curator = create_user("curator", UserRank.CURATOR)
	login_as(client, curator)

	# The package page offers the tags page rather than the edit page
	html = client_request(client, "GET", "/packages/owner/pkg/").data.decode("utf-8")
	assert 'href="/packages/owner/pkg/tags/"' in html
	assert 'href="/packages/owner/pkg/edit/"' not in html

	html = client_request(client, "GET", "/packages/owner/pkg/tags/").data.decode("utf-8")
	assert "Puzzle Game" in html

	rv = client_request(client, "POST", "/packages/owner/pkg/tags/",
			data={"categories": [str(puzzle.id)], "tags": [str(mapgen.id)]})
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/"
	assert tag_names(get_package()) == ["mapgen", "puzzle_game"]

	entry = AuditLogEntry.query.filter(AuditLogEntry.title.like("Edited pkg (Tags)%")).one()
	assert entry.causer.username == "curator"


def test_tags_page_rejects_tags_for_other_types(client):
	puzzle = make_category("Puzzle Game")
	create_package("pkg", create_user("owner"))
	login_as(client, create_user("curator", UserRank.CURATOR))

	# A mod isn't offered game categories
	html = client_request(client, "GET", "/packages/owner/pkg/tags/").data.decode("utf-8")
	assert "Puzzle Game" not in html

	rv = client_request(client, "POST", "/packages/owner/pkg/tags/", data={"categories": [str(puzzle.id)]})
	assert rv.status_code == 200
	assert tag_names(get_package()) == []


def test_curator_cant_edit_rest_of_package(client):
	package = create_package("pkg", create_user("owner"))
	curator = create_user("curator", UserRank.CURATOR)

	with pytest.raises(DomainError):
		do_edit_package(curator, package, False, False, {"title": "Changed", "tags": ["mapgen"]})
	assert get_package().title == "pkg"

	login_as(client, curator)
	rv = client_request(client, "POST", "/packages/owner/pkg/edit/", data={"title": "Changed"})
	assert rv.status_code == 403


@pytest.mark.parametrize("rank", [UserRank.MEMBER, UserRank.TRUSTED_MEMBER])
def test_tags_page_needs_curator(client, rank):
	create_package("pkg", create_user("owner"))
	login_as(client, create_user("stranger", rank))

	assert client_request(client, "GET", "/packages/owner/pkg/tags/").status_code == 403
	assert client_request(client, "POST", "/packages/owner/pkg/tags/", data={"tags": []}).status_code == 403


def test_maintainer_can_use_tags_page(client):
	owner = create_user("owner")
	create_package("pkg", owner)
	login_as(client, owner)

	mapgen = Tag.query.filter_by(name="mapgen").one()
	rv = client_request(client, "POST", "/packages/owner/pkg/tags/", data={"tags": [str(mapgen.id)]})

	assert rv.status_code == 302
	assert tag_names(get_package()) == ["mapgen"]


def test_curator_edits_tag_definitions(client):
	login_as(client, create_user("curator", UserRank.CURATOR))

	rv = client_request(client, "POST", "/tags/new/", data={"title": "Racing", "kind": "CATEGORY"})
	assert rv.status_code == 302

	rv = client_request(client, "POST", "/tags/racing/edit/",
			data={"title": "Racing", "name": "racing", "kind": "CATEGORY", "icon": "fa-flag-checkered"})
	assert rv.status_code == 302
	db.session.expire_all()
	assert Tag.query.filter_by(name="racing").one().icon == "fa-flag-checkered"


def collection_form(title: str, name: str = "") -> dict:
	return {"title": title, "name": name, "short_description": "", "long_description": ""}


def test_curator_creates_and_edits_contentdb_collections(client):
	contentdb = User.query.filter_by(username="ContentDB").one()
	package = create_package("pkg", create_user("owner"))
	spotlight = create_collection(contentdb, [package], name="spotlight")
	login_as(client, create_user("curator", UserRank.CURATOR))

	rv = client_request(client, "POST", "/collections/new/?author=ContentDB", data=collection_form("Featured Games"))
	assert rv.status_code == 302
	db.session.expire_all()
	assert Collection.query.filter_by(author=contentdb, name="featured_games").count() == 1

	rv = client_request(client, "POST", "/collections/ContentDB/spotlight/edit/", data=collection_form("Spotlight!", "spotlight"))
	assert rv.status_code == 302
	db.session.expire_all()
	edited = db.session.get(Collection, spotlight.id)
	assert edited is not None and edited.title == "Spotlight!"

	# But not delete them, as some are used by the site
	html = client_request(client, "GET", "/collections/ContentDB/spotlight/").data.decode("utf-8")
	assert "/collections/ContentDB/spotlight/delete/" not in html
	assert client_request(client, "POST", "/collections/ContentDB/spotlight/delete/").status_code == 403
	assert db.session.get(Collection, spotlight.id) is not None


def test_curator_sees_create_button_on_contentdb_collections(client):
	login_as(client, create_user("curator", UserRank.CURATOR))

	html = client_request(client, "GET", "/collections/ContentDB/").data.decode("utf-8")
	assert "/collections/new/?author=ContentDB" in html

	html = client_request(client, "GET", "/collections/curator/").data.decode("utf-8")
	assert "/collections/new/?author=curator" in html


def test_curator_doesnt_see_create_button_on_other_users_collections(client):
	create_user("other")
	login_as(client, create_user("curator", UserRank.CURATOR))

	html = client_request(client, "GET", "/collections/other/").data.decode("utf-8")
	assert "/collections/new/?author=other" not in html


def test_create_collection_for_unknown_author_is_404(client):
	login_as(client, create_user("editor", UserRank.EDITOR))
	assert client_request(client, "GET", "/collections/new/?author=nobody").status_code == 404


def test_editor_sees_contentdb_collections_when_adding_package(client):
	contentdb = User.query.filter_by(username="ContentDB").one()
	package = create_package("pkg", create_user("owner"))
	create_collection(contentdb, [], name="spotlight")
	login_as(client, create_user("editor", UserRank.EDITOR))

	html = client_request(client, "GET", package.get_url("collections.package_add")).data.decode("utf-8")
	assert "Spotlight" in html


def test_member_doesnt_see_contentdb_collections_when_adding_package(client):
	contentdb = User.query.filter_by(username="ContentDB").one()
	package = create_package("pkg", create_user("owner"))
	create_collection(contentdb, [], name="spotlight")
	login_as(client, create_user("member", UserRank.MEMBER))

	html = client_request(client, "GET", package.get_url("collections.package_add")).data.decode("utf-8")
	assert "Spotlight" not in html


def test_curator_cant_edit_other_users_collections(client):
	other = create_user("other")
	create_collection(other, [], name="mine")
	login_as(client, create_user("curator", UserRank.CURATOR))

	assert client_request(client, "GET", "/collections/other/mine/edit/").status_code == 403
	assert client_request(client, "GET", "/collections/new/?author=other").status_code == 403


def test_curator_package_tags_list(client):
	create_package("pkg", create_user("owner"))
	login_as(client, create_user("curator", UserRank.CURATOR))

	# Linked from the profile dropdown
	html = client_request(client, "GET", "/").data.decode("utf-8")
	assert 'href="/todo/tags/"' in html

	# Each package links to its tags page, as curators can't use the edit page
	rv = client_request(client, "GET", "/todo/tags/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert 'href="/packages/owner/pkg/tags/"' in html
	assert 'href="/packages/owner/pkg/edit/"' not in html


def test_package_tags_list_not_linked_for_members(client):
	login_as(client, create_user("member"))

	html = client_request(client, "GET", "/").data.decode("utf-8")
	assert 'href="/todo/tags/"' not in html
