# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
from typing import Callable

import pytest

from app.models import db, User, UserRank, Thread, ThreadReply, PackageReview, PackageReviewVote, Collection, \
	APIToken, AuditLogEntry, AuditSeverity, ForumTopic, PackageType, UserSession, UserBan, Report, ReportCategory, \
	OAuthClient
from app.tasks.usertasks import delete_unused_users_without_email
from app.utils.misc import hash_token, random_string
from ..utils import make_package


TWO_YEARS_AGO = datetime.datetime.utcnow() - datetime.timedelta(days=730)


def make_unused_user(username: str) -> User:
	user = User(username)
	user.rank = UserRank.MEMBER
	user.created_at = TWO_YEARS_AGO
	db.session.add(user)
	return user


def get_admin() -> User:
	return User.query.filter_by(username="rubenwardy").one()


def make_thread(author: User) -> Thread:
	thread = Thread()
	thread.title = "Hello"
	thread.author = author
	db.session.add(thread)
	return thread


def make_review(author: User) -> PackageReview:
	review = PackageReview()
	review.package = make_package("reviewed", get_admin())
	review.author = author
	review.rating = 5
	db.session.add(review)
	return review


def add_email(user: User):
	user.email = "unused@example.com"


def add_package(user: User):
	make_package("owned", user)


def add_maintained_package(user: User):
	make_package("maintained", get_admin()).maintainers.append(user)


def add_review(user: User):
	make_review(user)


def add_reply(user: User):
	reply = ThreadReply()
	reply.thread = make_thread(get_admin())
	reply.author = user
	reply.comment = "Hello"
	db.session.add(reply)


def add_thread(user: User):
	make_thread(user)


def add_collection(user: User):
	collection = Collection()
	collection.author = user
	collection.name = "favorites"
	collection.title = "Favorites"
	collection.short_description = "My favorites"
	db.session.add(collection)


def add_token(user: User):
	token = APIToken()
	token.name = "test"
	token.owner = user
	token.access_token_hash = hash_token(random_string(32))
	db.session.add(token)


def add_recent_audit_log(user: User):
	db.session.add(AuditLogEntry(user, AuditSeverity.USER, "Logged in using GitHub OAuth", None))


def add_forum_topic(user: User):
	topic = ForumTopic()
	topic.topic_id = 1234
	topic.author = user
	topic.type = PackageType.MOD
	topic.title = "My mod"
	topic.posts = 1
	topic.views = 1
	db.session.add(topic)


def add_oauth_client(user: User):
	oauth_client = OAuthClient()
	oauth_client.id = random_string(24)
	oauth_client.title = "My app"
	oauth_client.secret_hash = hash_token(random_string(32))
	oauth_client.redirect_url = "https://example.com"
	oauth_client.owner = user
	db.session.add(oauth_client)


def add_report(user: User):
	report = Report()
	report.id = random_string(24)
	report.user = user
	report.category = ReportCategory.SPAM
	report.title = "Spam"
	report.message = "Spam"
	db.session.add(report)


def add_session(user: User):
	user_session = UserSession()
	user_session.user = user
	user_session.token_hash = hash_token(random_string(32))
	db.session.add(user_session)


def add_ban(user: User):
	user_ban = UserBan()
	user_ban.banned_by = get_admin()
	user_ban.message = "test"
	user_ban.expires_at = datetime.datetime.now() + datetime.timedelta(days=7)
	user.ban = user_ban


def make_banned(user: User):
	user.rank = UserRank.BANNED


def make_moderator(user: User):
	user.rank = UserRank.MODERATOR


def make_recent(user: User):
	user.created_at = datetime.datetime.utcnow() - datetime.timedelta(days=30)


@pytest.mark.parametrize("blocker", [
	add_email, add_package, add_maintained_package, add_review, add_reply, add_thread, add_collection, add_token,
	add_recent_audit_log, add_forum_topic, add_oauth_client, add_report, add_session, add_ban, make_banned,
	make_moderator, make_recent,
])
def test_used_user_is_kept(client, blocker: Callable[[User], None]):
	user = make_unused_user("used")
	blocker(user)
	db.session.commit()

	assert delete_unused_users_without_email() == 0
	assert User.query.filter_by(username="used").count() == 1


def test_unused_user_is_deleted(client):
	make_unused_user("unused")
	db.session.commit()
	user_count = User.query.count()

	assert delete_unused_users_without_email() == 1
	assert User.query.filter_by(username="unused").count() == 0
	assert User.query.count() == user_count - 1

	entry = AuditLogEntry.query.filter_by(title="Deleted unused user unused").one()
	assert entry.url == "/users/unused/"
	assert entry.causer.username == "ContentDB"
	assert entry.severity == AuditSeverity.MODERATION


def test_unused_user_with_null_created_at_is_deleted(client):
	user = make_unused_user("unused")
	db.session.commit()

	# Set after inserting, as the column default replaces None on insert
	user.created_at = None
	db.session.commit()

	assert delete_unused_users_without_email() == 1
	assert User.query.filter_by(username="unused").count() == 0


def test_old_audit_log_entries_do_not_block_deletion(client):
	user = make_unused_user("unused")
	entry = AuditLogEntry(user, AuditSeverity.USER, "Logged in using GitHub OAuth", None)
	entry.created_at = TWO_YEARS_AGO
	db.session.add(entry)
	db.session.commit()
	entry_id = entry.id

	assert delete_unused_users_without_email() == 1
	assert User.query.filter_by(username="unused").count() == 0

	db.session.expire_all()
	entry = AuditLogEntry.query.filter_by(id=entry_id).one()
	assert entry.causer_id is None


def test_user_with_review_votes_is_deleted(client):
	user = make_unused_user("unused")
	review = make_review(get_admin())
	vote = PackageReviewVote()
	vote.review = review
	vote.user = user
	vote.is_positive = True
	db.session.add(vote)
	db.session.commit()

	assert delete_unused_users_without_email() == 1
	assert User.query.filter_by(username="unused").count() == 0
	assert PackageReviewVote.query.count() == 0


def test_user_watching_thread_is_deleted(client):
	user = make_unused_user("unused")
	thread = make_thread(get_admin())
	thread.watchers.append(user)
	db.session.commit()
	thread_id = thread.id

	assert delete_unused_users_without_email() == 1
	assert User.query.filter_by(username="unused").count() == 0

	db.session.expire_all()
	assert Thread.query.filter_by(id=thread_id).one().watchers == []
