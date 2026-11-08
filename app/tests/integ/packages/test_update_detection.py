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
	AuditLogEntry
from app.tasks import importtasks
from ..factories import create_user, create_package


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
