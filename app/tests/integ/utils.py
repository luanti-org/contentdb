# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import pytest, json
from sqlalchemy import text

from app import app
from app.models import db, User
from app.default_data import populate


def clear_data(session):
	meta = db.metadata
	for table in reversed(meta.sorted_tables):
		session.execute(text(f'ALTER TABLE "{table.name}" DISABLE TRIGGER ALL;'))
		session.execute(table.delete())
		session.execute(text(f'ALTER TABLE "{table.name}" ENABLE TRIGGER ALL;'))


def recreate_db():
	clear_data(db.session)
	populate(db.session)
	db.session.commit()


def parse_json(b):
	return json.loads(b.decode("utf8"))


def is_type(t, v):
	return v and isinstance(v, t)


def is_optional(t, v):
	return not v or isinstance(v, t)


def is_str(v):
	return is_type(str, v)


def is_int(v):
	return is_type(int, v)


@pytest.fixture
def client():
	with app.app_context():
		app.config["TESTING"] = True
		app.config['WTF_CSRF_ENABLED'] = False

		recreate_db()
		assert User.query.count() == 2

		with app.test_client() as client:
			yield client

		app.config["TESTING"] = False
		app.config['WTF_CSRF_ENABLED'] = True


def validate_package_list(packages, strict=False):
	valid_keys = {
		"author", "name", "release",
		"short_description", "thumbnail",
		"title", "type"
	}

	for package in packages:
		assert set(package.keys()).issubset(valid_keys)

		assert is_str(package.get("author"))
		assert is_str(package.get("name"))
		if strict:
			assert is_int(package.get("release"))
		else:
			assert is_optional(int, package.get("release"))
		assert is_str(package.get("short_description"))
		assert is_optional(str, package.get("thumbnail"))
		assert is_str(package.get("title"))
		assert is_str(package.get("type"))


def login(client, username, password):
	return client.post("/user/login/", data=dict(
			username=username,
			password=password,
	), follow_redirects=True)


def logout(client):
	return client.post("/user/logout/", follow_redirects=True)


def is_logged_in(rv):
	return b"/user/login/" not in rv.data and b"/user/logout/" in rv.data
