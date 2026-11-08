# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest
from limits.errors import StorageError

from app import app
from app.default_data import populate_test_data
from app.domain.DomainError import DomainError
from app.domain.releases import check_can_create_release, do_create_zip_release, _record_release
from app.models import db, User, UserRank, Thread, ThreadReply
from app.utils import ratelimit
from app.utils.ratelimit import RateLimit
from app.utils.user import make_flask_login_password
from ..utils import login, make_package


def test_hit_until_full(client):
	limit = RateLimit("test", ["2 per minute"])
	assert limit.test()
	assert limit.hit()
	assert limit.hit()
	assert not limit.test()
	assert not limit.hit()


def test_keys_are_separate(client):
	assert RateLimit("test/a", ["1 per minute"]).hit()
	assert not RateLimit("test/a", ["1 per minute"]).hit()
	assert RateLimit("test/b", ["1 per minute"]).hit()


def test_all_windows_must_have_room(client):
	assert RateLimit("test", ["1 per minute"]).hit()

	limit = RateLimit("test", ["5 per hour", "1 per minute"])
	assert not limit.hit()

	# The failed hit didn't record anything in the hourly window
	assert RateLimit("test", ["1 per hour"]).hit()


def test_no_windows_is_unlimited(client):
	limit = RateLimit("test", [])
	for _ in range(100):
		assert limit.hit()


def test_allows_when_storage_is_down(client, monkeypatch):
	def fail(*args, **kwargs):
		raise StorageError(Exception("Redis is down"))

	monkeypatch.setattr(ratelimit._limiter, "test", fail)
	monkeypatch.setattr(ratelimit._limiter, "hit", fail)

	limit = RateLimit("test", ["1 per minute"])
	assert limit.test()
	assert limit.hit()
	assert limit.hit()


def _make_user(username: str, rank: UserRank) -> User:
	user = User(username, True)
	user.rank = rank
	db.session.add(user)
	return user


def _create_release(user: User, package, name: str):
	"""Does what creating a release does to the rate limits, without making a release"""
	_record_release(check_can_create_release(user, package, name, name))


def test_checking_a_release_does_not_count(client):
	user = _make_user("releaser", UserRank.MEMBER)
	package = make_package("ratelimited", user)
	db.session.commit()

	for i in range(10):
		check_can_create_release(user, package, f"1.{i}", f"1.{i}")


def test_zip_release_with_bad_commit_hash_does_not_count(client):
	user = _make_user("releaser", UserRank.MEMBER)
	package = make_package("ratelimited", user)
	db.session.commit()

	for i in range(10):
		with pytest.raises(DomainError) as e:
			do_create_zip_release(user, package, f"1.{i}", None, None, None, commit_hash="not a hash")
		assert e.value.code == 400

	check_can_create_release(user, package, "2.0", "2.0")


def test_release_limit_per_package(client):
	user = _make_user("releaser", UserRank.MEMBER)
	package = make_package("ratelimited", user)
	db.session.commit()

	for i in range(7):
		_create_release(user, package, f"1.{i}")

	with pytest.raises(DomainError) as e:
		check_can_create_release(user, package, "1.7", "1.7")
	assert e.value.code == 429

	# Other packages have their own limit
	other = make_package("other", user)
	db.session.commit()
	check_can_create_release(user, other, "1.0", "1.0")


def test_release_rejected_for_other_reasons_does_not_count(client):
	user = _make_user("releaser", UserRank.MEMBER)
	package = make_package("ratelimited", user)
	db.session.commit()

	for _ in range(10):
		with pytest.raises(DomainError) as e:
			check_can_create_release(user, package, "not a version", "title")
		assert e.value.code == 403

	check_can_create_release(user, package, "1.0", "1.0")


@pytest.mark.parametrize("rank, limited", [
	(UserRank.MEMBER, True),
	(UserRank.TRUSTED_MEMBER, False),
])
def test_release_limit_per_user(client, rank, limited):
	user = _make_user("releaser", rank)
	packages = [make_package(f"pkg{i}", user) for i in range(7)]
	db.session.commit()

	for i in range(30):
		_create_release(user, packages[i // 5], f"1.{i}")

	if limited:
		with pytest.raises(DomainError) as e:
			check_can_create_release(user, packages[6], "2.0", "2.0")
		assert e.value.code == 429
	else:
		check_can_create_release(user, packages[6], "2.0", "2.0")


def _login_new_member(client, rank: UserRank = UserRank.NEW_MEMBER) -> User:
	user = _make_user("commenter", rank)
	user.password = make_flask_login_password("password")
	db.session.commit()
	login(client, "commenter", "password")
	return user


def test_comment_limit_survives_deletion(client):
	populate_test_data(db.session)
	user = _login_new_member(client)

	thread = Thread()
	thread.title = "Some thread"
	thread.author = User.query.filter_by(username="rubenwardy").one()
	db.session.add(thread)

	first_reply = ThreadReply()
	first_reply.thread = thread
	first_reply.author = thread.author
	first_reply.comment = "The first post"
	db.session.add(first_reply)
	db.session.commit()

	url = f"/threads/{thread.id}/"
	for i in range(2):
		client.post(url, data=dict(comment=f"Comment number {i}"))
	assert ThreadReply.query.filter_by(author=user).count() == 2

	# Deleting the comments doesn't free up the limit
	ThreadReply.query.filter_by(author=user).delete()
	db.session.commit()
	assert not user.can_comment_ratelimit()

	rv = client.post(url, data=dict(comment="One comment too many"), follow_redirects=True)
	assert b"Please wait before commenting again" in rv.data
	assert ThreadReply.query.filter_by(author=user).count() == 0


def test_comment_with_blocked_link_does_not_count(client, monkeypatch):
	monkeypatch.setitem(app.config, "BLOCKED_DOMAINS", ["blocked.example"])
	populate_test_data(db.session)
	user = _login_new_member(client)

	thread = Thread()
	thread.title = "Some thread"
	thread.author = User.query.filter_by(username="rubenwardy").one()
	db.session.add(thread)

	first_reply = ThreadReply()
	first_reply.thread = thread
	first_reply.author = thread.author
	first_reply.comment = "The first post"
	db.session.add(first_reply)
	db.session.commit()

	url = f"/threads/{thread.id}/"
	for _ in range(3):
		rv = client.post(url, data=dict(comment="See https://blocked.example/page"))
		assert b"Linking to blocked sites is not allowed" in rv.data

	for i in range(2):
		client.post(url, data=dict(comment=f"Comment number {i}"))
	assert ThreadReply.query.filter_by(author=user).count() == 2


def test_open_thread_limit(client):
	populate_test_data(db.session)
	user = _login_new_member(client)
	url = "/packages/Jeija/mesecons/threads/new/"

	for i in range(2):
		client.post(url, data=dict(title=f"Thread {i}", comment="This is a long enough comment"))
	assert Thread.query.filter_by(author=user).count() == 2

	client.post(url, data=dict(title="Thread 3", comment="This is a long enough comment"))
	assert Thread.query.filter_by(author=user).count() == 2


@pytest.mark.parametrize("rank, per_minute", [
	(UserRank.NEW_MEMBER, 3),
	(UserRank.MEMBER, 5),
	(UserRank.TRUSTED_MEMBER, 5),
])
def test_getmeta_limit(client, monkeypatch, rank, per_minute):
	from app.blueprints import tasks

	class FakeResult:
		id = "fake"

	monkeypatch.setattr(tasks.get_meta, "delay", lambda *args: FakeResult())
	_login_new_member(client, rank)

	for _ in range(per_minute):
		rv = client.post("/tasks/getmeta/new/?url=https://github.com/a/b")
		assert rv.status_code == 200

	rv = client.post("/tasks/getmeta/new/?url=https://github.com/a/b")
	assert rv.status_code == 429
	assert "error" in rv.json
