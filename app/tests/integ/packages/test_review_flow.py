# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Writing, editing, deleting, approving and voting on reviews, and how they affect package scores.
"""

import pytest

from app.models import db, User, UserRank, Package, PackageState, PackageReview, PackageReviewVote, Thread, \
	AuditLogEntry, AuditSeverity, Notification, NotificationType, Language
from app.tasks.pkgtasks import update_package_scores
from ..factories import create_user, create_package, create_review, create_review_vote, login_as, client_request


@pytest.fixture
def setup(client) -> Package:
	language = Language()
	language.id = "en"
	language.title = "English"
	db.session.add(language)
	owner = create_user("owner")
	create_user("member")
	create_user("new_member", UserRank.NEW_MEMBER)
	create_user("trusted", UserRank.TRUSTED_MEMBER)
	create_user("editor", UserRank.EDITOR)
	create_user("moderator", UserRank.MODERATOR)
	create_user("admin", UserRank.ADMIN)
	return create_package("pkg", owner, maintainers=[create_user("maintainer")])


def as_user(client, username: str):
	login_as(client, User.query.filter_by(username=username).one())


def review_form(**extra):
	return {
		"title": "Great package",
		"language": "en",
		"comment": "I really enjoyed using this package",
		"rating": "5",
		**extra,
	}


def post_review(client, **extra):
	return client_request(client, "POST", "/packages/owner/pkg/review/", data=review_form(**extra))


def get_package() -> Package:
	db.session.expire_all()
	return Package.query.filter_by(name="pkg").one()


def get_review(username: str) -> PackageReview:
	db.session.expire_all()
	return PackageReview.query.filter(PackageReview.author.has(username=username)).one()


def test_create_review(client, setup):
	as_user(client, "member")

	rv = post_review(client)

	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/owner/pkg/"
	review = get_review("member")
	assert review.approved
	assert review.rating == 5
	assert review.language.id == "en"
	thread = review.thread
	assert thread.title == "Great package"
	assert not thread.private
	assert thread.first_reply.comment == "I really enjoyed using this package"
	assert [x.username for x in thread.watchers] == ["member"]
	# A positive review adds 150 to the score
	assert get_package().score == 150
	assert AuditLogEntry.query.filter_by(title="Created review of pkg: Great package").count() == 1
	notifications = Notification.query.filter_by(title="New review 'Great package'").all()
	assert {x.user.username for x in notifications} == {"owner", "maintainer"}
	assert {x.type for x in notifications} == {NotificationType.NEW_REVIEW}


@pytest.mark.parametrize("rating,score", [("5", 150), ("3", 0), ("1", -150)])
def test_review_score(client, setup, rating, score):
	as_user(client, "member")
	post_review(client, rating=rating)
	assert get_package().score == score


def test_edit_review(client, setup):
	as_user(client, "member")
	post_review(client)

	rv = post_review(client, title="Changed my mind", rating="1", comment="It broke my world, sadly")

	assert rv.status_code == 302
	assert PackageReview.query.count() == 1
	review = get_review("member")
	assert review.rating == 1
	assert review.thread.title == "Changed my mind"
	assert review.thread.first_reply.comment == "It broke my world, sadly"
	assert Thread.query.count() == 1
	assert get_package().score == -150
	assert AuditLogEntry.query.filter_by(title="Edited review of pkg: Changed my mind").count() == 1
	assert Notification.query.filter_by(title="Updated review 'Changed my mind'").count() == 2


@pytest.mark.parametrize("username", ["owner", "maintainer"])
def test_cant_review_own_package(client, setup, username):
	as_user(client, username)

	rv = post_review(client)

	assert rv.status_code == 302
	assert PackageReview.query.count() == 0


def test_cant_review_unapproved_package(client, setup):
	setup.state = PackageState.WIP
	db.session.commit()
	as_user(client, "member")

	assert post_review(client).status_code == 404
	assert PackageReview.query.count() == 0


def test_review_validation(client, setup):
	as_user(client, "member")

	rv = post_review(client, comment="Too short")

	assert rv.status_code == 200
	assert PackageReview.query.count() == 0


@pytest.mark.parametrize("username,comment,sensitive,approved", [
	("new_member", "I really enjoyed using this package", False, True),
	# Links from new members are held for moderation, as they could be spam
	("new_member", "See https://example.com for my thoughts", False, False),
	("member", "See https://example.com for my thoughts", False, True),
	# Reviews of sensitive packages are held unless written by trusted members
	("member", "I really enjoyed using this package", True, False),
	("trusted", "I really enjoyed using this package", True, True),
])
def test_review_needs_approval(client, setup, username, comment, sensitive, approved):
	setup.sensitive_package = sensitive
	db.session.commit()
	as_user(client, username)

	post_review(client, comment=comment)

	review = get_review(username)
	assert review.approved == approved
	assert review.thread.private == (not approved)
	# Unapproved reviews don't count towards the score
	assert get_package().score == (150 if approved else 0)


def test_delete_own_review(client, setup):
	review = create_review(User.query.filter_by(username="member").one(), setup, comment="Original comment")
	thread_id = review.thread.id
	as_user(client, "member")

	rv = client_request(client, "POST", "/packages/owner/pkg/reviews/member/delete/")

	assert rv.status_code == 302
	assert rv.headers["Location"] == f"/threads/{thread_id}/"
	assert PackageReview.query.count() == 0
	# The comments are kept as a thread
	thread = db.session.get(Thread, thread_id)
	assert thread is not None
	db.session.refresh(thread)
	assert thread.review is None
	replies = thread.replies.all()
	assert replies[0].comment == "Original comment"
	assert replies[-1].comment == "_converted review into a thread_"
	assert replies[-1].is_status_update
	assert get_package().score == 0
	entry = AuditLogEntry.query.filter_by(title="Converted review by member to thread").one()
	assert entry.severity == AuditSeverity.NORMAL


def test_moderator_deletes_review(client, setup):
	create_review(User.query.filter_by(username="member").one(), setup)
	as_user(client, "moderator")

	client_request(client, "POST", "/packages/owner/pkg/reviews/member/delete/")

	assert PackageReview.query.count() == 0
	assert AuditLogEntry.query.filter_by(title="Converted review by member to thread").one().severity == \
		AuditSeverity.MODERATION


@pytest.mark.parametrize("username,reviewer,status", [
	("editor", "member", 403),
	("owner", "member", 403),
	("moderator", "nobody", 404),
])
def test_delete_review_denied(client, setup, username, reviewer, status):
	create_review(User.query.filter_by(username="member").one(), setup)
	as_user(client, username)

	rv = client_request(client, "POST", f"/packages/owner/pkg/reviews/{reviewer}/delete/")

	assert rv.status_code == status
	assert PackageReview.query.count() == 1


def test_approve_review(client, setup):
	review = create_review(User.query.filter_by(username="new_member").one(), setup, approved=False)
	review.language = db.session.get(Language, "en")
	db.session.commit()
	assert get_package().score == 0
	as_user(client, "moderator")

	rv = client_request(client, "POST", "/packages/owner/pkg/reviews/new_member/approve/")

	assert rv.status_code == 302
	review = get_review("new_member")
	assert review.approved
	assert not review.thread.private
	assert get_package().score == 150
	assert AuditLogEntry.query.filter_by(title="Approved review by new_member").one().severity == \
		AuditSeverity.MODERATION


@pytest.mark.parametrize("username,approved,status", [
	("editor", False, 403),
	("moderator", True, 404),
])
def test_approve_review_denied(client, setup, username, approved, status):
	create_review(User.query.filter_by(username="new_member").one(), setup, approved=approved)
	as_user(client, username)

	rv = client_request(client, "POST", "/packages/owner/pkg/reviews/new_member/approve/")

	assert rv.status_code == status
	assert get_review("new_member").approved == approved


def vote(client, review: PackageReview, is_positive: str, json: bool = False, next_url: str | None = None):
	url = f"/packages/owner/pkg/review/{review.id}/" + (f"?r={next_url}" if next_url else "")
	headers = {"Accept": "application/json"} if json else {}
	return client_request(client, "POST", url, data={"is_positive": is_positive}, headers=headers)


def test_vote_on_review(client, setup):
	review = create_review(User.query.filter_by(username="member").one(), setup)
	as_user(client, "trusted")

	vote(client, review, "yes")
	assert get_review("member").score == 4

	# Voting the same way again removes the vote
	vote(client, review, "yes")
	assert get_review("member").score == 1
	assert PackageReviewVote.query.count() == 0

	vote(client, review, "yes")
	vote(client, review, "no")
	assert get_review("member").score == -2
	assert [x.is_positive for x in PackageReviewVote.query.all()] == [False]


@pytest.mark.parametrize("username,error", [
	("owner", "You can't vote on the reviews on your own package!"),
	("member", "You can't vote on your own reviews!"),
])
def test_vote_denied(client, setup, username, error):
	review = create_review(User.query.filter_by(username="member").one(), setup)
	as_user(client, username)

	rv = vote(client, review, "yes", json=True)

	assert rv.status_code == 403
	assert rv.json == {"success": False, "error": error}
	assert PackageReviewVote.query.count() == 0


@pytest.mark.parametrize("next_url,expected", [
	("/packages/owner/pkg/", "/packages/owner/pkg/"),
	("https://evil.example/", None),
])
def test_vote_redirect(client, setup, next_url, expected):
	review = create_review(User.query.filter_by(username="member").one(), setup)
	as_user(client, "trusted")

	rv = vote(client, review, "yes", next_url=next_url)

	assert rv.status_code == 302
	assert rv.headers["Location"] == (expected or f"/threads/{review.thread.id}/")


@pytest.mark.parametrize("username,status", [("moderator", 403), ("admin", 200)])
def test_review_votes_page(client, setup, username, status):
	review = create_review(User.query.filter_by(username="member").one(), setup)
	create_review_vote(review, User.query.filter_by(username="trusted").one())
	as_user(client, username)

	rv = client_request(client, "GET", "/packages/owner/pkg/review-votes/")

	assert rv.status_code == status
	if status == 200:
		assert "trusted" in rv.data.decode("utf-8")


def test_update_package_scores(client, setup):
	"""
	The daily task decays download scores, then adds review scores back on.
	"""
	setup.score_downloads = 100
	db.session.commit()
	create_review(User.query.filter_by(username="member").one(), setup, rating=5)
	create_review(User.query.filter_by(username="trusted").one(), setup, rating=1)
	create_review(User.query.filter_by(username="new_member").one(), setup, rating=5, approved=False)

	update_package_scores.apply()

	package = get_package()
	assert package.score_downloads == pytest.approx(93)
	# +150 and -150 cancel out, and the unapproved review is left out
	assert package.score == pytest.approx(93)
