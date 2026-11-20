# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
The /packages/ page. Its query only loads what package tiles use (QueryBuilder.build_package_query(for_tiles=True)),
and other columns raise when accessed, so these render tiles in each state to catch a tile using something unloaded.
"""

from app.models import db, Language, PackageState, PackageTranslation, PackageType
from ..factories import create_package, create_release, create_review, create_screenshot, create_user, login_as


def test_package_list(client):
	author = create_user("author")
	author.display_name = "Author Display Name"
	reviewer = create_user("reviewer")
	mod = create_package("Some_Mod", author)
	mod.short_desc = "A short description of the mod"
	screenshot = create_screenshot(mod)
	create_review(reviewer, mod)
	create_package("Some_Game", author, type=PackageType.GAME)
	create_package("Wip_Mod", author, state=PackageState.WIP)
	db.session.commit()

	rv = client.get("/packages/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")

	assert html.count("packagecard") == 2
	assert "Some_Mod" in html and "Some_Game" in html and "Wip_Mod" not in html
	assert "Author Display Name" in html
	assert "A short description of the mod" in html
	assert screenshot.get_thumb_url() in html
	assert 'href="/packages/author/some_mod/"' in html


def test_package_list_filters_and_sorts(client):
	author = create_user("author")
	mod = create_package("Some_Mod", author)
	create_release(mod)
	create_package("Some_Game", author, type=PackageType.GAME)

	for url in ["/packages/?type=game", "/packages/?sort=last_release", "/packages/?sort=reviews",
			"/packages/?q=Some", "/packages/?random=1"]:
		rv = client.get(url)
		assert rv.status_code == 200, url

	html = client.get("/packages/?type=game").data.decode("utf-8")
	assert "Some_Game" in html and "Some_Mod" not in html


def test_package_list_lucky(client):
	author = create_user("author")
	create_package("Some_Mod", author)

	# Not using q=, as search doesn't match in the test database (see the commented-out test in api/test_api.py)
	rv = client.get("/packages/?type=mod&lucky=1")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/author/some_mod/"


def test_package_list_translated(client):
	author = create_user("author")
	mod = create_package("Some_Mod", author)
	language = Language()
	language.id = "de"
	language.title = "Deutsch"
	db.session.add(language)
	translation = PackageTranslation()
	translation.package = mod
	translation.language = language
	translation.title = "Ein Mod"
	translation.short_desc = "Eine kurze Beschreibung"
	db.session.add(translation)
	db.session.commit()

	rv = client.get("/packages/", headers={"Accept-Language": "de"})
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "Ein Mod" in html
	assert "Eine kurze Beschreibung" in html


def test_package_list_logged_in(client):
	author = create_user("author")
	create_package("Some_Mod", author)
	login_as(client, author)

	rv = client.get("/packages/")
	assert rv.status_code == 200
	assert b"Some_Mod" in rv.data
