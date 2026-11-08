# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Git update detection: check_update_config, with the git calls stubbed.
"""

import datetime
from typing import Any

import pytest
from sqlalchemy import text

from app.models import db, Package, PackageUpdateConfig, PackageUpdateTrigger, PackageRelease, ReleaseState, \
	Notification, AuditLogEntry
from app.blueprints.packages import releases as release_routes
from app.tasks import importtasks
from ..factories import create_user, create_package, create_release, login_as, client_request


OLD = "a" * 40
NEW = "b" * 40


class GitStub:
	def __init__(self, monkeypatch):
		self.commit: str | None = NEW
		self.tag: tuple[str | None, str | None, str | None] = ("v2.0", NEW, "Tag notes")
		self.commit_calls: list[tuple[str, str | None]] = []
		self.queued: list[dict[str, Any]] = []

		monkeypatch.setattr(importtasks, "get_latest_commit", self.get_latest_commit)
		monkeypatch.setattr(importtasks, "get_latest_tag", lambda url: self.tag)
		monkeypatch.setattr(importtasks.make_vcs_release, "apply_async", self.apply_async)

	def get_latest_commit(self, url: str, ref: str | None):
		self.commit_calls.append((url, ref))
		return self.commit

	def apply_async(self, args, task_id):
		release_id, commit = args
		# Look from a separate connection, which only sees committed rows
		with db.engine.connect() as conn:
			committed = conn.execute(text("SELECT count(*) FROM package_release WHERE id = :id"),
					{"id": release_id}).scalar() == 1
		self.queued.append({"release_id": release_id, "commit": commit, "task_id": task_id, "committed": committed})


@pytest.fixture
def git(monkeypatch) -> GitStub:
	return GitStub(monkeypatch)


def setup(trigger=PackageUpdateTrigger.COMMIT, make_release=False, last_commit: str | None = OLD,
		last_tag: str | None = "v1.0", ref: str | None = None) -> Package:
	owner = create_user("owner")
	package = create_package("pkg", owner, maintainers=[create_user("maintainer")])
	package.repo = "https://example.com/owner/pkg.git"
	config = PackageUpdateConfig()
	config.package = package
	config.trigger = trigger
	config.make_release = make_release
	config.ref = ref
	db.session.add(config)
	db.session.commit()
	# Set after inserting, as the defaults would replace None
	config.last_commit = last_commit
	config.last_tag = last_tag
	db.session.commit()
	return package


def check(package: Package) -> PackageUpdateConfig:
	result = importtasks.check_update_config.apply(args=[package.id])
	assert result.successful(), result.traceback
	db.session.expire_all()
	config = PackageUpdateConfig.query.get(package.id)
	assert config is not None
	return config


def notifications() -> list[tuple[str, str]]:
	return sorted((x.user.username, x.title) for x in Notification.query.all())


def test_first_check_only_records_commit(client, git):
	package = setup(last_commit=None, last_tag=None)

	config = check(package)

	assert (config.last_commit, config.last_tag) == (NEW, None)
	assert config.outdated_at is None
	assert config.last_checked_at is not None
	assert notifications() == []
	assert git.queued == []


def test_commit_uses_branch(client, git):
	package = setup(ref="main")
	check(package)
	assert git.commit_calls == [("https://example.com/owner/pkg.git", "main")]


def test_no_change(client, git):
	package = setup(last_commit=NEW)

	config = check(package)

	assert config.last_commit == NEW
	assert config.outdated_at is None
	assert notifications() == []


def test_no_commit_found(client, git):
	git.commit = None
	package = setup()

	config = check(package)

	assert config.last_commit == OLD
	assert notifications() == []


def test_new_commit_marks_outdated(client, git):
	package = setup()

	config = check(package)

	assert config.outdated_at is not None
	assert config.last_commit == NEW
	msg = "New commit bbbbb found on the Git repo, is the package outdated? The last commit was aaaaa"
	assert notifications() == [("maintainer", msg), ("owner", msg)]
	assert git.queued == []

	# Only notifies once while outdated
	git.commit = "c" * 40
	config = check(package)
	assert config.last_commit == "c" * 40
	assert len(notifications()) == 2


def test_new_tag_marks_outdated(client, git):
	package = setup(trigger=PackageUpdateTrigger.TAG)

	config = check(package)

	assert config.outdated_at is not None
	assert (config.last_commit, config.last_tag) == (NEW, "v2.0")
	msg = "New tag v2.0 found on the Git repo. The last tag was v1.0"
	assert notifications() == [("maintainer", msg), ("owner", msg)]


def test_tag_moved_to_same_commit(client, git):
	package = setup(trigger=PackageUpdateTrigger.TAG, last_commit=NEW, last_tag="v1.9")

	config = check(package)

	assert config.last_tag == "v2.0"
	assert config.outdated_at is None
	assert notifications() == []


def test_commit_already_released(client, git):
	package = setup()
	release = create_release(package, "2.0")
	release.commit_hash = NEW
	db.session.commit()

	config = check(package)

	# Left as it was, so the release isn't reported as new
	assert config.last_commit == OLD
	assert config.outdated_at is None
	assert notifications() == []


@pytest.mark.parametrize("trigger,name,notes", [
	(PackageUpdateTrigger.TAG, "v2.0", "Tag notes"),
	(PackageUpdateTrigger.COMMIT, datetime.datetime.utcnow().strftime("%Y-%m-%d"), None),
])
def test_make_release(client, git, trigger, name, notes):
	package = setup(trigger=trigger, make_release=True)

	config = check(package)

	[release] = PackageRelease.query.filter_by(package_id=package.id).all()
	assert (release.name, release.title, release.release_notes) == (name, name, notes)
	assert release.state == ReleaseState.PROCESSING
	assert config.last_commit == NEW
	assert config.outdated_at is None
	assert AuditLogEntry.query.filter_by(title=f"Created release {name} (Git Update Detection)").count() == 1

	[queued] = git.queued
	assert queued["release_id"] == release.id
	assert queued["commit"] == NEW
	assert queued["task_id"] == release.task_id
	# The import task must be able to find the release
	assert queued["committed"]


def test_git_disabled(client, git, monkeypatch):
	package = setup()
	monkeypatch.setattr(importtasks, "can_package_use_git", lambda package: False)

	result = importtasks.check_update_config.apply(args=[package.id])

	assert result.failed()
	assert "Git update detection is temporarily disabled" in str(result.result)
	db.session.expire_all()
	config = PackageUpdateConfig.query.get(package.id)
	assert config is not None
	assert config.last_commit == OLD
	assert config.task_id is not None


@pytest.fixture
def queued_checks(monkeypatch) -> list[int]:
	calls: list[int] = []
	monkeypatch.setattr(release_routes.check_update_config, "delay", lambda package_id: calls.append(package_id))
	return calls


@pytest.mark.parametrize("trigger,action,make_release", [
	("COMMIT", "notification", False),
	("TAG", "make_release", True),
])
def test_set_update_config(client, queued_checks, trigger, action, make_release):
	owner = create_user("owner")
	package = create_package("pkg", owner)
	package.repo = "https://example.com/owner/pkg.git"
	release = create_release(package, "1.0")
	release.commit_hash = OLD
	db.session.commit()
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/update-config/",
			data={"trigger": trigger, "action": action, "ref": ""})

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/releases/"
	db.session.expire_all()
	config = PackageUpdateConfig.query.get(package.id)
	assert config is not None
	assert config.trigger == PackageUpdateTrigger[trigger]
	assert config.make_release == make_release
	assert config.ref is None
	# New commits are compared against the last release, and tags against ones made after this
	assert config.last_commit == (OLD if trigger == "COMMIT" else None)
	assert queued_checks == [package.id]


def test_disable_update_config(client, queued_checks):
	package = setup()
	login_as(client, package.author)

	rv = client_request(client, "POST", "/packages/owner/pkg/update-config/",
			data={"trigger": "COMMIT", "action": "notification", "disable": "1"})

	assert rv.status_code == 302
	db.session.expire_all()
	assert PackageUpdateConfig.query.get(package.id) is None
	assert AuditLogEntry.query.filter_by(title="Deleted update configuration").count() == 1
	assert queued_checks == []


def test_update_config_needs_repo(client, queued_checks):
	owner = create_user("owner")
	create_package("pkg", owner)
	login_as(client, owner)

	rv = client_request(client, "POST", "/packages/owner/pkg/update-config/",
			data={"trigger": "COMMIT", "action": "notification"})

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/edit/"
	assert PackageUpdateConfig.query.count() == 0


def test_update_config_no_permission(client, queued_checks):
	package = setup()
	login_as(client, create_user("stranger"))

	rv = client_request(client, "POST", "/packages/owner/pkg/update-config/",
			data={"trigger": "COMMIT", "action": "make_release"})

	assert rv.status_code == 403
	db.session.expire_all()
	config = PackageUpdateConfig.query.get(package.id)
	assert config is not None
	assert not config.make_release
