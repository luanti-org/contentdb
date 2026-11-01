# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

import pytest

from app import app
from app.default_data import populate_test_data
from app.domain.DomainError import DomainError
from app.domain.git_access import can_user_use_git, can_package_use_git
from app.domain.releases import do_create_vcs_release
from app.models import db, User, UserRank, Package, PackageState, PackageUpdateConfig
from app.tasks import TaskError
from app.tasks.importtasks import check_update_config
from app.utils.user import make_flask_login_password
from .utils import login
from .utils import client # noqa


TRUSTED = UserRank.TRUSTED_MEMBER
MEMBER = UserRank.MEMBER
WIP = PackageState.WIP
APPROVED = PackageState.APPROVED


@pytest.fixture
def git_access(monkeypatch):
	def set_access(value: str):
		monkeypatch.setitem(app.config, "GIT_ACCESS", value)

	return set_access


def setup_package(author_rank: UserRank, maintainer_rank: UserRank,
		state: PackageState = PackageState.WIP) -> tuple[Package, User]:
	populate_test_data(db.session)

	package = Package.query.filter_by(name="mesecons").one()
	package.state = state
	package.author.rank = author_rank
	package.author.is_active = True

	maintainer = User("maintainer")
	maintainer.is_active = True
	maintainer.rank = maintainer_rank
	maintainer.email = "maintainer@example.com"
	maintainer.email_confirmed_at = datetime.datetime.now()
	maintainer.password = make_flask_login_password("password123")
	db.session.add(maintainer)
	package.maintainers.append(maintainer)
	db.session.commit()

	return package, maintainer


def test_defaults_to_none(client, monkeypatch):
	monkeypatch.delitem(app.config, "GIT_ACCESS", raising=False)
	package, maintainer = setup_package(TRUSTED, TRUSTED)

	assert not can_user_use_git(maintainer)
	assert not can_package_use_git(package)


@pytest.mark.parametrize("access,state,author_rank,user_rank,can_use_user,can_use_package", [
	("none", APPROVED, TRUSTED, TRUSTED, False, False),
	("none", WIP, MEMBER, MEMBER, False, False),
	("trusted", WIP, TRUSTED, TRUSTED, True, True),
	("trusted", WIP, TRUSTED, MEMBER, False, True),
	("trusted", WIP, MEMBER, TRUSTED, True, False),
	("trusted", WIP, MEMBER, MEMBER, False, False),
	("trusted", APPROVED, MEMBER, MEMBER, False, False),
	("trusted_or_approved", WIP, TRUSTED, TRUSTED, True, True),
	("trusted_or_approved", WIP, TRUSTED, MEMBER, False, True),
	("trusted_or_approved", WIP, MEMBER, TRUSTED, True, False),
	("trusted_or_approved", WIP, MEMBER, MEMBER, False, False),
	("trusted_or_approved", APPROVED, MEMBER, MEMBER, False, True),
	("trusted_or_approved", APPROVED, TRUSTED, MEMBER, False, True),
	("all", WIP, MEMBER, MEMBER, True, True),
])
def test_can_use_git(client, git_access, access, state, author_rank, user_rank, can_use_user, can_use_package):
	git_access(access)
	package, maintainer = setup_package(author_rank, user_rank, state)

	# Package access depends only on the author, so all maintainers have the same access
	assert can_user_use_git(maintainer) == can_use_user
	assert can_package_use_git(package) == can_use_package


@pytest.mark.parametrize("access", ["none", "trusted", "trusted_or_approved"])
def test_vcs_release_blocked(client, git_access, access):
	git_access(access)
	package, maintainer = setup_package(MEMBER, TRUSTED)

	with pytest.raises(DomainError) as e:
		do_create_vcs_release(maintainer, package, "v1.0.0", None, None, None)
	assert e.value.code == 503


@pytest.mark.parametrize("access,user_rank,allowed", [
	("none", TRUSTED, False),
	("trusted", MEMBER, False),
	("trusted", TRUSTED, True),
	("trusted_or_approved", MEMBER, False),
	("trusted_or_approved", TRUSTED, True),
	("all", MEMBER, True),
])
def test_getmeta(client, git_access, monkeypatch, access, user_rank, allowed):
	git_access(access)
	setup_package(TRUSTED, user_rank)
	login(client, "maintainer", "password123")

	calls = []

	class FakeResult:
		id = "fake"

	def fake_delay(*args):
		calls.append(args)
		return FakeResult()

	monkeypatch.setattr("app.blueprints.tasks.get_meta.delay", fake_delay)

	rv = client.post("/tasks/getmeta/new/?url=https://github.com/minetest-mods/mesecons")
	if allowed:
		assert rv.status_code == 200
		assert len(calls) == 1
	else:
		assert rv.status_code == 403
		assert len(calls) == 0

	rv = client.get("/packages/new/")
	assert rv.status_code == 200
	assert (b"package_create.js" in rv.data) == allowed


@pytest.mark.parametrize("access,enabled", [
	("none", False),
	("trusted", True),
	("all", True),
])
def test_release_form(client, git_access, access, enabled):
	git_access(access)
	package, _ = setup_package(TRUSTED, TRUSTED)
	login(client, "maintainer", "password123")

	rv = client.get(package.get_url("packages.create_release"))
	assert rv.status_code == 200

	assert (b"Creating releases using Git is temporarily disabled" in rv.data) == (not enabled)
	assert (b'value="vcs" checked' in rv.data) == enabled
	assert (b'value="vcs" disabled' in rv.data) == (not enabled)
	assert (b'value="upload" checked' in rv.data) == (not enabled)


def test_update_config_warning_uses_author(client, git_access):
	git_access("trusted")
	package, _ = setup_package(TRUSTED, MEMBER)
	login(client, "maintainer", "password123")

	rv = client.get(package.get_url("packages.update_config"))
	assert rv.status_code == 200
	assert b"Git Update Detection is temporarily disabled" not in rv.data

	package.author.rank = MEMBER
	db.session.commit()
	rv = client.get(package.get_url("packages.update_config"))
	assert b"Git Update Detection is temporarily disabled" in rv.data


def test_apply_all_reports_skipped(client, git_access):
	git_access("trusted")
	package, maintainer = setup_package(MEMBER, TRUSTED)
	package.update_config = PackageUpdateConfig()
	package.update_config.last_commit = "a" * 40
	package.update_config.last_tag = "v2.0.0"
	package.update_config.set_outdated()
	db.session.commit()
	login(client, "maintainer", "password123")

	rv = client.post("/users/maintainer/update-configs/apply-all/", follow_redirects=True)
	assert rv.status_code == 200
	assert b"Skipped 1 package" in rv.data
	assert package.releases.count() == 0


def test_check_update_config_records_error(client, git_access):
	git_access("none")
	package, _ = setup_package(TRUSTED, TRUSTED, APPROVED)
	package.update_config = PackageUpdateConfig()
	db.session.commit()

	with pytest.raises(TaskError):
		check_update_config.apply(args=(package.id,), throw=True)

	db.session.refresh(package.update_config)
	assert package.update_config.task_id is not None
