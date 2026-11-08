# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
User text in the hypertext shown in the Luanti client must be escaped, so it can't add actions or change
formatting.
"""

import re

from app.models import db
from ..factories import create_user, create_package, create_review, client_request


INJECTION = "</b><action name=x>"


def unescaped_actions(body: str) -> list[str]:
	return re.findall(r"(?<!\\)<action[^>]*>", body)


def test_package_info_escapes_display_names(client):
	owner = create_user("owner")
	maintainer = create_user("maintainer")
	maintainer.display_name = INJECTION
	db.session.commit()
	create_package("pkg", owner, maintainers=[maintainer])

	rv = client_request(client, "GET", "/api/packages/owner/pkg/for-client/?formspec_version=7")

	assert rv.status_code == 200
	assert rv.json is not None
	body = rv.json["info_hypertext"]["body"]
	assert r"\</b\>\<action name=x\>" in body
	assert unescaped_actions(body) == []


def test_reviews_escape_user_text(client):
	package = create_package("pkg", create_user("owner"))
	reviewer = create_user("reviewer")
	reviewer.display_name = INJECTION
	db.session.commit()
	review = create_review(reviewer, package, comment="Great <action name=y> mod")
	review.thread.title = "<big>Title</big>"
	db.session.commit()

	rv = client_request(client, "GET", "/api/packages/owner/pkg/for-client/reviews/?formspec_version=7")

	assert rv.status_code == 200
	assert rv.json is not None
	body = rv.json["body"]
	assert r"\<big\>Title\</big\>" in body
	assert r"\<action name=x\>" in body
	assert r"\<action name=y\>" in body
	# Leave a review, the reviewer's profile, and the comments link
	assert len(unescaped_actions(body)) == 3
