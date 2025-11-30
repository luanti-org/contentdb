# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from app.default_data import populate_test_data
from app.models import db
from .utils import client # noqa


def test_homepage_empty(client):
	"""Start with a blank database."""

	rv = client.get("/")
	assert b"No packages available" in rv.data and b"packagegridscrub" not in rv.data


def test_homepage_with_contents(client):
	"""Start with a test database."""

	populate_test_data(db.session)
	db.session.commit()

	rv = client.get("/")

	assert b"packagegridscrub" in rv.data
