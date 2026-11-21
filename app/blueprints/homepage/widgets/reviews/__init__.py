# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from typing import Any

from flask_babel import lazy_gettext
from flask_login import current_user
from sqlalchemy.orm import joinedload, load_only

from app.models import Language, Package, PackageReview, Thread, User, db
from ..base import Widget


class ReviewsWidget(Widget):
	"""Recent positive reviews"""

	template = "widgets/reviews/reviews.html"
	label = lazy_gettext("Recent reviews")
	default_limit = 5

	def get_scripts(self) -> list[str]:
		if current_user.is_authenticated:
			return ["/static/js/quick_review_voting.js?v=2"]
		return []

	def get_context(self) -> dict[str, Any]:
		reviews = (PackageReview.query
			.filter(PackageReview.rating > 3, PackageReview.approved == True)  # noqa: E712
			.options(
				load_only(PackageReview.id, PackageReview.rating, PackageReview.created_at, PackageReview.language_id,
						PackageReview.approved, raiseload=True),
				joinedload(PackageReview.author).load_only(User.username, User.rank, User.display_name,
						User.profile_pic, User.use_gravatar, User.email, User.is_active, raiseload=True),
				joinedload(PackageReview.votes),
				joinedload(PackageReview.language).load_only(Language.title, raiseload=True),
				joinedload(PackageReview.thread).load_only(Thread.title, Thread.replies_count, raiseload=True)
					.subqueryload(Thread.first_reply),
				joinedload(PackageReview.package)
					.load_only(Package.title, Package.name, raiseload=True)
					.joinedload(Package.author).load_only(User.username, User.display_name, raiseload=True))
			.order_by(db.desc(PackageReview.created_at))
			.limit(self.get_limit())
			.all())

		return {
			"reviews": reviews,
		}
