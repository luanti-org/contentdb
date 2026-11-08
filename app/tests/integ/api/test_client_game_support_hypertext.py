# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
The game support lines in the package info hypertext shown in the Luanti client.
"""

import re

from app.models import db, Package, PackageGameSupport, PackageType
from ..factories import create_user, create_package, client_request


def add_support(package: Package, game: Package, supports: bool):
	support = PackageGameSupport()
	support.package = package
	support.game = game
	support.supports = supports
	support.confidence = 2
	db.session.add(support)
	db.session.commit()


def get_line(body: str, label: str) -> str | None:
	match = re.search(rf"^{label}: (.*)$", body, re.MULTILINE)
	return match.group(1) if match else None


def get_info_body(client) -> str:
	rv = client_request(client, "GET", "/api/packages/owner/pkg/for-client/?formspec_version=7")
	assert rv.status_code == 200
	assert rv.json is not None
	return rv.json["info_hypertext"]["body"]


def make_games():
	owner = create_user("owner")
	package = create_package("pkg", owner)
	good = create_package("good_game", owner, type=PackageType.GAME)
	good.title = "Good Game"
	bad = create_package("bad_game", owner, type=PackageType.GAME)
	bad.title = "Bad Game"
	db.session.commit()
	return package, good, bad


def test_supports_all_games_lists_unsupported_games(client):
	package, good, bad = make_games()
	package.supports_all_games = True
	db.session.commit()
	add_support(package, good, True)
	add_support(package, bad, False)

	body = get_info_body(client)

	assert get_line(body, "Supported Games") == "<b>No specific game required</b>"
	unsupported = get_line(body, "Unsupported Games")
	assert unsupported is not None
	assert "Bad Game" in unsupported
	assert "Good Game" not in unsupported


def test_specific_games_hides_unsupported_games(client):
	package, good, bad = make_games()
	add_support(package, good, True)
	add_support(package, bad, False)

	body = get_info_body(client)

	supported = get_line(body, "Supported Games")
	assert supported is not None
	assert "Good Game" in supported
	assert "Bad Game" not in supported
	assert get_line(body, "Unsupported Games") is None
