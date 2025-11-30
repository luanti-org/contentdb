# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import Blueprint, render_template
from flask_login import current_user
from sqlalchemy import or_, and_

from app.models import User, Package, PackageState, db, License, PackageReview, Collection

bp = Blueprint("donate", __name__)


@bp.route("/donate/")
def donate():
	reviewed_packages = None
	if current_user.is_authenticated:
		reviewed_packages = Package.query.filter(
			Package.state == PackageState.APPROVED,
			or_(Package.reviews.any(and_(PackageReview.author_id == current_user.id, PackageReview.rating >= 3)),
				Package.collections.any(and_(Collection.author_id == current_user.id, Collection.name == "favorites"))),
			or_(Package.donate_url.isnot(None), Package.author.has(User.donate_url.isnot(None)))
		).order_by(db.asc(Package.title)).all()

	query = Package.query.filter(
			Package.license.has(License.is_foss == True),
			Package.media_license.has(License.is_foss == True),
			Package.state == PackageState.APPROVED,
			or_(Package.donate_url.isnot(None), Package.author.has(User.donate_url.isnot(None)))
	).order_by(db.desc(Package.score))

	packages_count = query.count()
	top_packages = query.limit(40).all()

	return render_template("donate/index.html",
			reviewed_packages=reviewed_packages, top_packages=top_packages, packages_count=packages_count)
