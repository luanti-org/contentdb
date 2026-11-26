# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
from typing import NamedTuple, Optional

from flask import Blueprint, make_response, render_template
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.models import db, Collection, Package, PackageRelease, PackageState, PackageType, ReleaseState, Tag, User
from app.utils.flask import abs_url_for, cached

bp = Blueprint("sitemap", __name__)


class SitemapEntry(NamedTuple):
	url: str
	lastmod: Optional[datetime.date] = None


def _get_packages() -> list[SitemapEntry]:
	last_release = (db.session.query(PackageRelease.package_id, func.max(PackageRelease.created_at).label("date"))
		.filter(PackageRelease.state == ReleaseState.APPROVED)
		.group_by(PackageRelease.package_id)
		.subquery())

	rows = (db.session.query(Package, last_release.c.date)
		.outerjoin(last_release, last_release.c.package_id == Package.id)
		.options(joinedload(Package.author))
		.filter(Package.state == PackageState.APPROVED)
		.order_by(db.desc(Package.score))
		.all())

	ret = []
	for package, release_date in rows:
		# A package changes far more often than this, but releases are the most meaningful change
		dates = [x for x in (release_date, package.approved_at) if x is not None]
		lastmod = max(dates).date() if dates else None
		ret.append(SitemapEntry(package.get_url("packages.view", absolute=True), lastmod))
		if package.type == PackageType.GAME:
			ret.append(SitemapEntry(package.get_url("packages.game_hub", absolute=True)))
	return ret


def _get_entries() -> list[SitemapEntry]:
	entries = [SitemapEntry(abs_url_for("homepage.home"))]
	entries.extend(SitemapEntry(abs_url_for("packages.list_all", type=type.to_name())) for type in PackageType)

	tags = (Tag.query
		.filter(Tag.packages.any(Package.state == PackageState.APPROVED))
		.order_by(db.asc(Tag.name))
		.all())
	entries.extend(SitemapEntry(abs_url_for("packages.list_all", tag=tag.name)) for tag in tags)

	entries.extend(_get_packages())

	# Profiles without packages are noindexed, see users.profile
	authors = (User.query
		.filter(User.packages.any(Package.state == PackageState.APPROVED))
		.order_by(db.asc(User.username))
		.all())
	entries.extend(SitemapEntry(abs_url_for("users.profile", username=user.username)) for user in authors)

	# Favorites are personal, see collections.get_or_create_favorites
	collections = (Collection.query
		.options(joinedload(Collection.author))
		.filter(Collection.private.is_(False), Collection.name != "favorites",
			Collection.packages.any(Package.state == PackageState.APPROVED))
		.order_by(db.asc(Collection.id))
		.all())
	entries.extend(SitemapEntry(abs_url_for("collections.view", author=collection.author.username,
		name=collection.name)) for collection in collections)

	return entries


@bp.route("/sitemap.xml")
@cached(6*60*60)
def sitemap():
	resp = make_response(render_template("sitemap/sitemap.xml", entries=_get_entries()))
	resp.mimetype = "application/xml"
	return resp
