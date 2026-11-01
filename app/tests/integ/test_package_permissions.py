# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import pytest

from app.default_data import populate_test_data
from app.models import db, User, UserRank, Package, PackageState, Permission
from .utils import client # noqa


@pytest.mark.parametrize("username,rank,can_change_name", [
	("Jeija", UserRank.MEMBER, True),
	("maintainer", UserRank.MEMBER, True),
	("other", UserRank.MEMBER, False),
	("other", UserRank.APPROVER, False),
	("other", UserRank.EDITOR, True),
])
def test_change_name_requires_maintainer(client, username, rank, can_change_name):
	populate_test_data(db.session)

	package = Package.query.filter_by(name="mesecons").one()
	package.state = PackageState.WIP

	user = User.query.filter_by(username=username).first()
	if user is None:
		user = User(username)
		db.session.add(user)
		if username == "maintainer":
			package.maintainers.append(user)
	user.rank = rank
	user.is_active = True
	db.session.commit()

	assert package.check_perm(user, Permission.CHANGE_NAME) == can_change_name

	package.state = PackageState.APPROVED
	db.session.commit()

	assert not package.check_perm(user, Permission.CHANGE_NAME)
