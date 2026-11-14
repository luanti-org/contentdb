# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Editing game support, which re-checks the latest release.
"""

from typing import Any

from app.blueprints.packages import packages as package_routes
from app.models import db, PackageType
from ..factories import create_user, create_package, create_release, login_as, client_request


def test_enabling_detection_rechecks_release_with_causer(client, monkeypatch):
	calls: list[dict[str, Any]] = []
	monkeypatch.setattr(package_routes.check_zip_release, "apply_async",
			lambda args, task_id: calls.append({"args": args, "task_id": task_id}))

	owner = create_user("owner")
	package = create_package("pkg", owner, type=PackageType.TXP)
	package.enable_game_support_detection = False
	release = create_release(package)
	db.session.commit()
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/support/",
			data={"enable_support_detection": "y", "supported": "", "unsupported": ""})

	assert rv.status_code == 302
	[call] = calls
	assert rv.headers["Location"].startswith(f"/tasks/{call['task_id']}/")
	# The causer is shown in malicious content alerts
	assert call["args"] == (release.id, owner.id)
