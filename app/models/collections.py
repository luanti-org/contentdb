# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

from flask import url_for, current_app

from . import db, Permission, User, UserRank


class CollectionPackage(db.Model):
	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), primary_key=True)
	package = db.relationship("Package", foreign_keys=[package_id])

	collection_id = db.Column(db.Integer, db.ForeignKey("collection.id"), primary_key=True)
	collection = db.relationship("Collection", back_populates="items", foreign_keys=[collection_id])

	order = db.Column(db.Integer, nullable=False, default=0)
	description = db.Column(db.String, nullable=True)
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	collection_description_nonempty = db.CheckConstraint("description = NULL OR description != ''")

	def as_dict(self):
		return {
			"package": self.package.as_short_dict(current_app.config["BASE_URL"]),
			"order": self.order,
			"description": self.description,
			"created_at": self.created_at.isoformat(),
		}


class Collection(db.Model):
	id = db.Column(db.Integer, primary_key=True)

	author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author = db.relationship("User", back_populates="collections", foreign_keys=[author_id])

	name = db.Column(db.Unicode(100), nullable=False)
	title = db.Column(db.Unicode(100), nullable=False)
	short_description = db.Column(db.Unicode(200), nullable=False)
	long_description = db.Column(db.UnicodeText, nullable=True)
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
	private = db.Column(db.Boolean, nullable=False, default=False)
	pinned = db.Column(db.Boolean, nullable=False, default=False)

	packages = db.relationship("Package", secondary=CollectionPackage.__table__, backref="collections")
	items = db.relationship("CollectionPackage", back_populates="collection", order_by=db.asc("order"),
		cascade="all, delete, delete-orphan")

	collection_name_valid = db.CheckConstraint("name ~* '^[a-z0-9_]+$' AND name != '_game'")
	__table_args__ = (db.UniqueConstraint("author_id", "name", name="_collection_uc"),)

	def get_url(self, endpoint, **kwargs):
		return url_for(endpoint, author=self.author.username, name=self.name, **kwargs)

	def as_short_dict(self):
		return {
			"author": self.author.username,
			"name": self.name,
			"title": self.title,
			"short_description": self.short_description,
			"created_at": self.created_at.isoformat(),
			"private": self.private,
			"package_count": len(self.packages)
		}

	def as_dict(self):
		return {
			"author": self.author.username,
			"name": self.name,
			"title": self.title,
			"short_description": self.short_description,
			"long_description": self.long_description,
			"created_at": self.created_at.isoformat(),
			"private": self.private,
		}

	def check_perm(self, user: User, perm):
		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to Collection.check_perm()")

		if user is None or not user.is_authenticated:
			return perm == Permission.VIEW_COLLECTION and not self.private

		can_view = not self.private or self.author == user or user.rank.at_least(UserRank.MODERATOR)
		if perm == Permission.VIEW_COLLECTION:
			return can_view
		elif perm == Permission.EDIT_COLLECTION:
			return can_view and (self.author == user or user.rank.at_least(UserRank.EDITOR))
		else:
			raise Exception("Permission {} is not related to collections".format(perm.name))
