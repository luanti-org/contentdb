# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import Blueprint, jsonify, render_template, make_response
from flask_babel import gettext

from app.markdown import render_markdown
from app.models import Package, PackageState, db, PackageRelease, ReleaseState
from app.utils import is_package_page, abs_url_for, cached, cors_allowed

bp = Blueprint("feeds", __name__)


def _make_feed(title: str, feed_url: str, items: list):
	return {
		"version": "https://jsonfeed.org/version/1",
		"title": title,
		"description": gettext("Welcome to the best place to find Luanti mods, games, and texture packs"),
		"home_page_url": "https://content.luanti.org/",
		"feed_url": feed_url,
		"icon": "https://content.luanti.org/favicon-128.png",
		"expired": False,
		"items": items,
	}


def _render_link(url: str):
	return f"<p><a href='{url}'>Read more</a></p>"


def _get_new_packages_feed(feed_url: str) -> dict:
	packages = (Package.query
		.filter(Package.state == PackageState.APPROVED)
		.order_by(db.desc(Package.approved_at))
		.limit(100)
		.all())

	items = [{
			"id": package.get_url("packages.view", absolute=True),
			"language": "en",
			"title": f"New: {package.title}",
			"content_html": render_markdown(package.desc) \
				if package.desc else _render_link(package.get_url("packages.view", absolute=True)),
			"author": {
				"name": package.author.display_name,
				"avatar": package.author.get_profile_pic_url(absolute=True),
				"url": abs_url_for("users.profile", username=package.author.username),
			},
			"image": package.get_thumb_url(level=4, abs=True, format="png"),
			"url": package.get_url("packages.view", absolute=True),
			"summary": package.short_desc,
			"date_published": package.approved_at.isoformat(timespec="seconds") + "Z",
			"tags": ["new_package"],
		} for package in packages]

	return _make_feed(gettext("ContentDB new packages"), feed_url, items)


def _get_releases_feed(query, feed_url: str):
	releases = (query
		.filter(PackageRelease.package.has(state=PackageState.APPROVED), PackageRelease.state == ReleaseState.APPROVED)
		.order_by(db.desc(PackageRelease.created_at))
		.limit(250)
		.all())

	items = [{
			"id": release.package.get_url("packages.view_release", id=release.id, absolute=True),
			"language": "en",
			"title": f"\"{release.package.title}\" updated: {release.title}",
			"content_html": render_markdown(release.release_notes) \
				if release.release_notes else _render_link(release.package.get_url("packages.view_release", id=release.id, absolute=True)),
			"author": {
				"name": release.package.author.display_name,
				"avatar": release.package.author.get_profile_pic_url(absolute=True),
				"url": abs_url_for("users.profile", username=release.package.author.username),
			},
			"url": release.package.get_url("packages.view_release", id=release.id, absolute=True),
			"image": release.package.get_thumb_url(level=4, abs=True, format="png"),
			"summary": release.summary,
			"date_published": release.created_at.isoformat(timespec="seconds") + "Z",
			"tags": ["release"],
		} for release in releases]

	return _make_feed(gettext("ContentDB package updates"), feed_url, items)


def _get_all_feed(feed_url: str):
	releases = _get_releases_feed(PackageRelease.query, "")["items"]
	packages = _get_new_packages_feed("")["items"]
	items = releases + packages
	items.sort(reverse=True, key=lambda x: x["date_published"])

	return _make_feed(gettext("ContentDB all"), feed_url, items)


def _atomify(feed):
	resp = make_response(render_template("feeds/json_to_atom.xml", feed=feed))
	resp.headers["Content-type"] = "application/atom+xml; charset=utf-8"
	return resp


@bp.route("/feeds/all.json")
@cors_allowed
@cached(1800)
def all_json():
	feed = _get_all_feed(abs_url_for("feeds.all_json"))
	return jsonify(feed)


@bp.route("/feeds/all.atom")
@cors_allowed
@cached(1800)
def all_atom():
	feed = _get_all_feed(abs_url_for("feeds.all_atom"))
	return _atomify(feed)


@bp.route("/feeds/packages.json")
@cors_allowed
@cached(1800)
def packages_all_json():
	feed = _get_new_packages_feed(abs_url_for("feeds.packages_all_json"))
	return jsonify(feed)


@bp.route("/feeds/packages.atom")
@cors_allowed
@cached(1800)
def packages_all_atom():
	feed = _get_new_packages_feed(abs_url_for("feeds.packages_all_atom"))
	return _atomify(feed)


@bp.route("/feeds/releases.json")
@cors_allowed
@cached(1800)
def releases_all_json():
	feed = _get_releases_feed(PackageRelease.query, abs_url_for("feeds.releases_all_json"))
	return jsonify(feed)


@bp.route("/feeds/releases.atom")
@cors_allowed
@cached(1800)
def releases_all_atom():
	feed = _get_releases_feed(PackageRelease.query, abs_url_for("feeds.releases_all_atom"))
	return _atomify(feed)


@bp.route("/packages/<author>/<name>/releases_feed.json")
@cors_allowed
@is_package_page
@cached(1800)
def releases_package_json(package: Package):
	feed = _get_releases_feed(package.releases, package.get_url("feeds.releases_package_json", absolute=True))
	return jsonify(feed)


@bp.route("/packages/<author>/<name>/releases_feed.atom")
@cors_allowed
@is_package_page
@cached(1800)
def releases_package_atom(package: Package):
	feed = _get_releases_feed(package.releases, package.get_url("feeds.releases_package_atom", absolute=True))
	return _atomify(feed)
