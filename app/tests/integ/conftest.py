# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Fixtures shared by all integration tests.
"""

import pytest

from app import app
from app.models import User
from app.utils.ratelimit import storage as ratelimit_storage
from .utils import recreate_db


@pytest.fixture
def client():
	"""
	A test client with a freshly populated database. Most integration tests need this.
	CSRF is disabled, so forms can be posted without a token.
	"""
	with app.app_context():
		app.config["TESTING"] = True
		app.config['WTF_CSRF_ENABLED'] = False

		recreate_db()
		assert User.query.count() == 2
		ratelimit_storage.reset()

		with app.test_client() as client:
			yield client

		app.config["TESTING"] = False
		app.config['WTF_CSRF_ENABLED'] = True
