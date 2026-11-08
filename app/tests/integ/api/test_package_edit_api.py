# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Editing packages through the API, with PUT /api/packages/<author>/<name>/.
"""

import pytest

from app.models import db, Package, PackageState, Tag, ContentWarning
from ..factories import create_user, create_package, create_token, client_request


URL = "/api/packages/owner/pkg/"


def setup(state: PackageState = PackageState.APPROVED) -> tuple[Package, str]:
	owner = create_user("owner")
	package = create_package("pkg", owner, state=state)
	_, access_token = create_token(owner, package)
	return package, access_token


def put(client, access_token: str | None, data):
	headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
	return client_request(client, "PUT", URL, headers=headers, json=data)


def get_package() -> Package:
	db.session.expire_all()
	return Package.query.filter_by(name="pkg").one()


@pytest.mark.parametrize("field,model", [("tags", Tag), ("content_warnings", ContentWarning)])
def test_edit_package_unknown_id(client, field, model):
	_, access_token = setup()
	missing_id = (db.session.query(db.func.max(model.id)).scalar() or 0) + 1000

	rv = put(client, access_token, {field: [missing_id]})

	assert rv.status_code == 400
	assert rv.json == {"success": False, "error": f"Unknown {'tag' if field == 'tags' else 'warning'}: {missing_id}"}
	assert getattr(get_package(), field) == []
