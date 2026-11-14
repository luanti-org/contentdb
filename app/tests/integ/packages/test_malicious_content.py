# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 rubenwardy <rw@rubenwardy>

import datetime
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest

from app.default_data import populate_test_data
from app.domain.moderation import REJECTED_MESSAGE
from app.models import db, User, UserRank, UserSession, Package, PackageState, PackageRelease, \
	ReleaseState, AuditLogEntry, ThreadReply
from app.tasks import TaskError, MaliciousContentError
from app.tasks import importtasks
from app.utils.models import get_system_user


REASON = "Submodule name is not allowed: '../../modules/evil'"


@pytest.fixture
def webhook(monkeypatch):
	mock = MagicMock()
	monkeypatch.setattr(importtasks.post_discord_webhook, "delay", mock)
	return mock


@pytest.fixture
def evil_zip(tmp_path, monkeypatch):
	archive = tmp_path / "evil.zip"
	with ZipFile(archive, "w") as zf:
		zf.writestr("mod.conf", "name = mesecons\n")
		zf.writestr("../evil.txt", "evil")

	monkeypatch.setattr(PackageRelease, "file_path", property(lambda self: str(archive)))
	return archive


@pytest.fixture
def malicious_git(monkeypatch):
	def clone_repo(*args, **kwargs):
		raise MaliciousContentError(REASON)

	monkeypatch.setattr(importtasks, "can_package_use_git", lambda package: True)
	monkeypatch.setattr(importtasks, "clone_repo", clone_repo)


def setup(state: PackageState, rank: UserRank = UserRank.MEMBER) -> tuple[User, PackageRelease]:
	populate_test_data(db.session)

	package = Package.query.filter_by(name="mesecons").one()
	package.state = state

	causer = package.author
	causer.rank = rank
	causer.is_active = True

	user_session = UserSession()
	user_session.user = causer
	user_session.token_hash = "a" * 64
	db.session.add(user_session)

	release = PackageRelease()
	release.package = package
	release.name = "v1"
	release.title = "v1"
	release.upload_path = "/uploads/v1.zip"
	release.created_at = datetime.datetime.now()
	db.session.add(release)
	db.session.commit()

	return causer, release


def run(task, *args) -> TaskError:
	with pytest.raises(TaskError) as e:
		task.apply(args=args, throw=True)
	return e.value


def assert_no_leak(release: PackageRelease, error: TaskError, expected: str):
	assert error.value == expected

	replies = ThreadReply.query.filter_by(author=get_system_user()).all()
	assert len(replies) == 1
	assert expected in replies[0].comment
	assert "evil" not in replies[0].comment
	assert "traversal" not in replies[0].comment

	# Maintainers can see the package's audit log
	assert AuditLogEntry.query.filter_by(package=release.package).count() == 0
	assert AuditLogEntry.query.filter(AuditLogEntry.title.like("Malicious content detected%")).count() == 1


def assert_not_banned(causer: User):
	db.session.refresh(causer)
	assert not causer.is_banned
	assert UserSession.query.filter_by(user=causer).count() == 1


def assert_alerted(webhook: MagicMock, *contains: str):
	webhook.assert_called_once()
	username, message, is_queue = webhook.call_args.args
	assert is_queue is True
	for text in contains:
		assert text in message


@pytest.mark.parametrize("state", [PackageState.WIP, PackageState.APPROVED])
def test_zip_traversal_alerts(client, webhook, evil_zip, state):
	causer, release = setup(state)

	error = run(importtasks.check_zip_release, release.id, causer.id)

	db.session.refresh(release)
	assert release.state == ReleaseState.FAILED
	assert_not_banned(causer)
	assert_no_leak(release, error, REJECTED_MESSAGE)
	assert_alerted(webhook, "path traversal", f"triggered by {causer.username}")


def test_zip_traversal_without_causer(client, webhook, evil_zip):
	causer, release = setup(PackageState.WIP)

	error = run(importtasks.check_zip_release, release.id)

	assert_not_banned(causer)
	assert_no_leak(release, error, REJECTED_MESSAGE)
	assert_alerted(webhook, "path traversal", "triggered by unknown")


def test_zip_other_failure_isnt_malicious(client, webhook, tmp_path, monkeypatch):
	archive = tmp_path / "bad.zip"
	with ZipFile(archive, "w") as zf:
		zf.writestr("bad\nname.txt", "")
	monkeypatch.setattr(PackageRelease, "file_path", property(lambda self: str(archive)))
	causer, release = setup(PackageState.WIP)

	error = run(importtasks.check_zip_release, release.id, causer.id)

	# An ordinary failure, so the reason is shown to the user
	assert "invalid characters" in error.value
	assert str(archive) not in error.value

	db.session.refresh(release)
	assert release.state == ReleaseState.FAILED
	replies = ThreadReply.query.filter_by(author=get_system_user()).all()
	assert len(replies) == 1
	assert "invalid characters" in replies[0].comment

	webhook.assert_not_called()
	assert AuditLogEntry.query.filter(AuditLogEntry.title.like("Malicious content detected%")).count() == 0


@pytest.mark.parametrize("state", [PackageState.WIP, PackageState.APPROVED])
def test_git_alerts(client, webhook, malicious_git, state):
	causer, release = setup(state)

	error = run(importtasks.make_vcs_release, release.id, None, causer.id)

	db.session.refresh(release)
	assert release.state == ReleaseState.FAILED
	assert_not_banned(causer)
	assert_no_leak(release, error, REJECTED_MESSAGE)
	assert_alerted(webhook, REASON, f"triggered by {causer.username}")


def test_git_without_causer(client, webhook, malicious_git):
	causer, release = setup(PackageState.WIP)

	error = run(importtasks.make_vcs_release, release.id, None)

	assert_not_banned(causer)
	assert_no_leak(release, error, REJECTED_MESSAGE)
	assert_alerted(webhook, REASON, "triggered by unknown")


def test_task_page_hides_malicious_reason(client, monkeypatch):
	result = MagicMock()
	result.status = "FAILURE"
	result.result = MaliciousContentError(REASON)
	result.traceback = REASON
	monkeypatch.setattr("app.blueprints.tasks.celery.AsyncResult", lambda id: result)

	rv = client.get("/tasks/abc/", headers={"Accept": "application/json"})
	assert rv.json["error"] == "Unknown server error"
	assert "evil" not in rv.get_data(as_text=True)
