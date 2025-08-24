# ContentDB
# Copyright (C) 2018-23 rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from flask import Blueprint, render_template, redirect
from sqlalchemy import and_

from app.models import Package, PackageReview, Thread, User, PackageState, db, PackageType, PackageRelease, Tags, Tag, \
	Collection, License, Language

bp = Blueprint("homepage", __name__)

from sqlalchemy.orm import joinedload, subqueryload, load_only, noload
from sqlalchemy.sql.expression import func


PKGS_PER_ROW = 4

# GAMEJAM_BANNER = "https://jam.luanti.org/img/banner.png"
#
# class GameJam:
# 	cover_image = type("", (), dict(url=GAMEJAM_BANNER))()
# 	tags = []
#
# 	def get_cover_image_url(self):
# 		return GAMEJAM_BANNER
#
# 	def get_url(self, _name):
# 		return "/gamejam/"
#
# 	title = "Luanti Game Jam 2023: \"Unexpected\""
# 	author = None
#
# 	short_desc = "The game jam has finished! It's now up to the community to play and rate the games."
# 	type = type("", (), dict(value="Competition"))()
# 	content_warnings = []
# 	reviews = []


@bp.route("/gamejam/")
def gamejam():
	return redirect("https://jam.luanti.org/")


@bp.route("/")
def home():
	def package_load(query):
		return query.options(
				load_only(Package.name, Package.title, Package.short_desc, Package.state, raiseload=True),
				subqueryload(Package.main_screenshot),
				joinedload(Package.author).load_only(User.username, User.display_name, raiseload=True),
				joinedload(Package.license).load_only(License.name, License.is_foss, raiseload=True),
				joinedload(Package.media_license).load_only(License.name, License.is_foss, raiseload=True))

	def package_spotlight_load(query):
		return query.options(
				load_only(Package.name, Package.title, Package.type, Package.short_desc, Package.state, Package.cover_image_id, raiseload=True),
				subqueryload(Package.main_screenshot),
				joinedload(Package.tags),
				joinedload(Package.content_warnings),
				joinedload(Package.author).load_only(User.username, User.display_name, raiseload=True),
				subqueryload(Package.cover_image),
				joinedload(Package.license).load_only(License.name, License.is_foss, raiseload=True),
				joinedload(Package.media_license).load_only(License.name, License.is_foss, raiseload=True))

	def review_load(query):
		return query.options(
			load_only(PackageReview.id, PackageReview.rating, PackageReview.created_at, PackageReview.language_id, raiseload=True),
			joinedload(PackageReview.author).load_only(User.username, User.rank, User.email, User.display_name, User.profile_pic, User.is_active, raiseload=True),
			joinedload(PackageReview.votes),
			joinedload(PackageReview.language).load_only(Language.title, raiseload=True),
			joinedload(PackageReview.thread).load_only(Thread.title, Thread.replies_count, raiseload=True).subqueryload(Thread.first_reply),
			joinedload(PackageReview.package)
				.load_only(Package.title, Package.name, raiseload=True)
				.joinedload(Package.author).load_only(User.username, User.display_name, raiseload=True))

	query = Package.query.filter_by(state=PackageState.APPROVED)
	count = db.session.query(Package.id).filter(Package.state == PackageState.APPROVED).count()

	spotlight_pkgs = package_spotlight_load(query.filter(
			Package.collections.any(and_(Collection.name == "spotlight", Collection.author.has(username="ContentDB"))))
		.order_by(func.random())).limit(6).all()
	# spotlight_pkgs.insert(0, GameJam())

	new = package_load(query).order_by(db.desc(Package.approved_at)).limit(PKGS_PER_ROW).all() # 0.06
	pop_mod = package_load(query).filter_by(type=PackageType.MOD).order_by(db.desc(Package.score)).limit(2*PKGS_PER_ROW).all()
	pop_gam = package_load(query).filter_by(type=PackageType.GAME).order_by(db.desc(Package.score)).limit(2*PKGS_PER_ROW).all()
	pop_txp = package_load(query).filter_by(type=PackageType.TXP).order_by(db.desc(Package.score)).limit(2*PKGS_PER_ROW).all()

	high_reviewed = package_load(query.order_by(db.desc(Package.score - Package.score_downloads))
			.filter(Package.reviews.any()).limit(PKGS_PER_ROW)).all()

	recent_releases_query = (
		db.session.query(
			Package.id,
			func.max(PackageRelease.created_at).label("max_created_at")
		)
		.join(PackageRelease, Package.releases)
		.group_by(Package.id)
		.order_by(db.desc("max_created_at"))
		.limit(3*PKGS_PER_ROW)
		.subquery())

	updated = (
		package_load(db.session.query(Package)
			.select_from(recent_releases_query)
			.join(Package, Package.id == recent_releases_query.c.id)
			.filter(Package.state == PackageState.APPROVED)
			.limit(PKGS_PER_ROW))
			.all())

	reviews = review_load(PackageReview.query.filter(PackageReview.rating > 3)
			.order_by(db.desc(PackageReview.created_at))).limit(5).all()

	downloads_result = db.session.query(func.sum(Package.downloads)).one_or_none()
	downloads = 0 if not downloads_result or not downloads_result[0] else downloads_result[0]

	tags = db.session.query(func.count(Tags.c.tag_id), Tag) \
		.select_from(Tag).outerjoin(Tags).join(Package).filter(Package.state == PackageState.APPROVED)\
		.group_by(Tag.id).order_by(db.asc(Tag.title)).all()

	return render_template("index.html", count=count, downloads=downloads, tags=tags, spotlight_pkgs=spotlight_pkgs,
			new=new, updated=updated, pop_mod=pop_mod, pop_txp=pop_txp, pop_gam=pop_gam, high_reviewed=high_reviewed,
			reviews=reviews)
