# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from app.models import db, User, Package, PackageReview, PackageReviewVote, UserBan, Thread, ThreadReply
from app.utils.models import get_system_user


def delete_user(user: User):
	"""
	Deletes a user and the packages they authored, without committing.

	Model cascades remove the user's content, such as threads, replies, reviews, votes and collections, and everything
	belonging to their packages. Audit log entries and reports are kept, with the user or package set to NULL.
	Report threads and the user's comments in them are kept, and reassigned to the system user.
	"""
	# Reviews and packages whose stored scores depend on the user's votes and reviews
	voted_reviews = (PackageReview.query
			.filter(PackageReview.votes.any(PackageReviewVote.user_id == user.id),
				PackageReview.author_id != user.id,
				PackageReview.package.has(Package.author_id != user.id))
			.all())
	reviewed_packages = (Package.query
			.filter(Package.reviews.any(PackageReview.author_id == user.id), Package.author_id != user.id)
			.all())

	system_user = get_system_user()

	# Keep bans issued by the user, such as a former moderator. The ban is also recorded in the audit log.
	UserBan.query.filter_by(banned_by_id=user.id).update({"banned_by_id": system_user.id},
			synchronize_session="fetch")

	# Keep report threads for moderation. These are reassigned before deleting, so the cascades don't reach them.
	for thread in Thread.query.filter(Thread.author_id == user.id, Thread.report.any()).all():
		thread.author = system_user
	for reply in ThreadReply.query.filter(ThreadReply.author_id == user.id, ThreadReply.thread.has(Thread.report.any())).all():
		reply.author = system_user
	db.session.flush()

	db.session.delete(user)
	db.session.flush()

	for review in voted_reviews:
		db.session.expire(review, ["votes"])
		review.update_score()

	for package in reviewed_packages:
		package.recalculate_score()
