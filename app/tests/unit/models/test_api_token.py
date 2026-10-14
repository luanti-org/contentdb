# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from unittest.mock import MagicMock

from app.models import APIToken


def make_user(is_banned=False):
	user = MagicMock()
	user.is_banned = is_banned
	return user


def make_package(author, maintainers=None):
	package = MagicMock()
	package.author = author
	package.maintainers = [author] + (maintainers or [])
	return package


def make_token(owner, package=None, client=None):
	token = MagicMock()
	token.owner = owner
	token.package = package
	token.client = client
	return token


def can_operate(token, package) -> bool:
	return APIToken.can_operate_on_package(token, package)


def test_author_can_operate():
	author = make_user()
	package = make_package(author)

	assert can_operate(make_token(author), package)
	assert can_operate(make_token(author, package=package), package)


def test_maintainer_needs_scoped_token():
	author = make_user()
	maintainer = make_user()
	package = make_package(author, [maintainer])

	assert not can_operate(make_token(maintainer), package)
	assert can_operate(make_token(maintainer, package=package), package)


def test_other_user_cannot_operate():
	author = make_user()
	maintainer = make_user()
	other = make_user()
	package = make_package(author, [maintainer])

	assert not can_operate(make_token(other), package)
	assert not can_operate(make_token(other, package=package), package)


def test_token_scoped_to_other_package():
	author = make_user()
	maintainer = make_user()
	package = make_package(author, [maintainer])
	other_package = make_package(author, [maintainer])

	assert not can_operate(make_token(author, package=other_package), package)
	assert not can_operate(make_token(maintainer, package=other_package), package)


def test_banned_user_cannot_operate():
	author = make_user(is_banned=True)
	maintainer = make_user(is_banned=True)
	package = make_package(author, [maintainer])

	assert not can_operate(make_token(author), package)
	assert not can_operate(make_token(author, package=package), package)
	assert not can_operate(make_token(maintainer, package=package), package)


def test_oauth_client_token_cannot_operate():
	author = make_user()
	maintainer = make_user()
	package = make_package(author, [maintainer])

	assert not can_operate(make_token(author, client=MagicMock()), package)
	assert not can_operate(make_token(maintainer, client=MagicMock()), package)
