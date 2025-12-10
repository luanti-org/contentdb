# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
from typing import Tuple, List

from flask import url_for
from sqlalchemy import select, func, text
from sqlalchemy.orm import column_property

from . import db
from .users import Permission, UserRank, User
from .packages import Package

watchers = db.Table("watchers",
	db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
	db.Column("thread_id", db.Integer, db.ForeignKey("thread.id"), primary_key=True)
)


class Thread(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=True)
	package    = db.relationship("Package", foreign_keys=[package_id], back_populates="threads")

	is_review_thread = db.relationship("Package", foreign_keys=[Package.review_thread_id], back_populates="review_thread")

	review_id  = db.Column(db.Integer, db.ForeignKey("package_review.id"), nullable=True)
	review     = db.relationship("PackageReview", foreign_keys=[review_id], cascade="all, delete")

	author_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author     = db.relationship("User", back_populates="threads", foreign_keys=[author_id])

	title      = db.Column(db.String(100), nullable=False)
	private    = db.Column(db.Boolean, server_default="0", nullable=False)

	locked     = db.Column(db.Boolean, server_default="0", nullable=False)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	replies    = db.relationship("ThreadReply", back_populates="thread", lazy="dynamic",
			order_by=db.asc("thread_reply_id"), cascade="all, delete, delete-orphan")

	watchers   = db.relationship("User", secondary=watchers, backref="watching")

	report = db.relationship("Report", foreign_keys="Report.thread_id", back_populates="thread", lazy="dynamic")

	first_reply = db.relationship("ThreadReply", uselist=False, foreign_keys="ThreadReply.thread_id",
			lazy=True, order_by=db.asc("id"), viewonly=True,
			primaryjoin="Thread.id==ThreadReply.thread_id")

	replies_count = column_property(select(func.count(text("thread_reply.id")))
			.select_from(text("thread_reply"))
			.where(text("thread_reply.thread_id") == id)
			.as_scalar())

	def get_description(self):
		comment = self.first_reply.comment.replace("\r\n", " ").replace("\n", " ").replace("  ", " ")
		if len(comment) > 100:
			return comment[:97] + "..."
		else:
			return comment

	def get_view_url(self, absolute=False):
		if absolute:
			from app.utils import abs_url_for
			return abs_url_for("threads.view", id=self.id)
		else:
			return url_for("threads.view", id=self.id, _external=False)

	def get_subscribe_url(self):
		return url_for("threads.subscribe", id=self.id)

	def get_unsubscribe_url(self):
		return url_for("threads.unsubscribe", id=self.id)

	def check_perm(self, user, perm):
		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to Thread.check_perm()")

		if user is None or not user.is_authenticated:
			return perm == Permission.SEE_THREAD and not self.private

		isMaintainer = user == self.author or (self.package is not None and self.package.author == user)
		if self.package:
			isMaintainer = isMaintainer or user in self.package.maintainers

		canSee = not self.private or isMaintainer or user.rank.at_least(UserRank.APPROVER) or user in self.watchers

		if perm == Permission.SEE_THREAD:
			return canSee

		elif perm == Permission.COMMENT_THREAD:
			return canSee and (not self.locked or user.rank.at_least(UserRank.MODERATOR))

		elif perm == Permission.LOCK_THREAD:
			return user.rank.at_least(UserRank.MODERATOR)

		elif perm == Permission.DELETE_THREAD:
			from app.utils.models import get_system_user
			return (self.author == get_system_user() and self.package and
					user in self.package.maintainers) or user.rank.at_least(UserRank.MODERATOR)

		else:
			raise Exception("Permission {} is not related to threads".format(perm.name))

	def get_visible_to(self) -> list[User]:
		retval = {
			self.author.username: self.author
		}

		for user in self.watchers:
			retval[user.username] = user

		if self.package:
			for user in self.package.maintainers:
				retval[user.username] = user

		return list(retval.values())

	def get_latest_reply(self):
		return ThreadReply.query.filter_by(thread_id=self.id).order_by(db.desc(ThreadReply.id)).first()


class ThreadReply(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	thread_id  = db.Column(db.Integer, db.ForeignKey("thread.id"), nullable=False)
	thread = db.relationship("Thread", back_populates="replies", foreign_keys=[thread_id])

	comment    = db.Column(db.String(2000), nullable=False)

	author_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author     = db.relationship("User", back_populates="replies", foreign_keys=[author_id])

	is_status_update = db.Column(db.Boolean, server_default="0", nullable=False)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	def get_url(self, absolute=False):
		return self.thread.get_view_url(absolute) + "#reply-" + str(self.id)

	def check_perm(self, user, perm):
		if user is None or not user.is_authenticated:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to ThreadReply.check_perm()")

		if perm == Permission.EDIT_REPLY:
			return user.rank.at_least(UserRank.NEW_MEMBER if user == self.author else UserRank.MODERATOR) and not self.thread.locked

		elif perm == Permission.DELETE_REPLY:
			return user.rank.at_least(UserRank.MODERATOR) and self.thread.first_reply != self

		else:
			raise Exception("Permission {} is not related to threads".format(perm.name))


class PackageReview(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
	package    = db.relationship("Package", foreign_keys=[package_id], back_populates="reviews")

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	author_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author     = db.relationship("User", foreign_keys=[author_id], back_populates="reviews")

	language_id = db.Column(db.String, db.ForeignKey("language.id"), nullable=True, default=None)
	language    = db.relationship("Language", foreign_keys=[language_id])

	rating     = db.Column(db.Integer, nullable=False)

	thread     = db.relationship("Thread", uselist=False, back_populates="review")
	votes      = db.relationship("PackageReviewVote", back_populates="review", cascade="all, delete, delete-orphan")

	score      = db.Column(db.Integer, nullable=False, default=1)

	def get_totals(self, current_user = None) -> Tuple[int,int,bool]:
		votes: List[PackageReviewVote] = self.votes
		pos = sum([ 1 for vote in votes if vote.is_positive ])
		neg = sum([ 1 for vote in votes if not vote.is_positive])
		user_vote = next(filter(lambda vote: vote.user == current_user, votes), None)
		return pos, neg, user_vote.is_positive if user_vote else None

	def as_dict(self, include_package=False):
		from app.utils import abs_url_for

		pos, neg, _user = self.get_totals()
		ret = {
			"is_positive": self.rating > 3,
			"rating": self.rating,
			"user": {
				"username": self.author.username,
				"display_name": self.author.display_name,
			},
			"created_at": self.created_at.isoformat(),
			"votes": {
				"helpful": pos,
				"unhelpful": neg,
			},
			"title": self.thread.title,
			"comment": self.thread.first_reply.comment,
			"thread": {
				"id": self.thread.id,
				"url": abs_url_for("threads.view", id=self.thread.id),
			},
		}
		if include_package:
			ret["package"] = self.package.as_key_dict()
		return ret

	def as_weight(self):
		"""
		From (1, 5) to (-1 to 1)
		"""
		return (self.rating - 3.0) / 2.0

	def get_edit_url(self):
		return self.package.get_url("packages.review")

	def get_delete_url(self):
		return url_for("packages.delete_review",
				author=self.package.author.username,
				name=self.package.name,
				reviewer=self.author.username)

	def get_vote_url(self, next_url=None):
		return url_for("packages.review_vote",
				author=self.package.author.username,
				name=self.package.name,
				review_id=self.id,
				r=next_url)

	def update_score(self):
		(pos, neg, _) = self.get_totals()
		self.score = 3 * (pos - neg) + 1

	def check_perm(self, user, perm):
		if user is None or not user.is_authenticated:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to PackageReview.check_perm()")

		if perm == Permission.DELETE_REVIEW:
			return user == self.author or user.rank.at_least(UserRank.MODERATOR)
		else:
			raise Exception("Permission {} is not related to reviews".format(perm.name))


class PackageReviewVote(db.Model):
	review_id = db.Column(db.Integer, db.ForeignKey("package_review.id"), primary_key=True)
	review = db.relationship("PackageReview", foreign_keys=[review_id], back_populates="votes")
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
	user = db.relationship("User", foreign_keys=[user_id], back_populates="review_votes")

	is_positive = db.Column(db.Boolean, nullable=False)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
