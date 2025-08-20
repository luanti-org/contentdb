# ContentDB
# Copyright (C) 2018-21  rubenwardy
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

import math
import os
from typing import List

import flask_sqlalchemy
from flask import request, jsonify, current_app
from flask_babel import gettext
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import func

from app import csrf
from app.logic.graphs import get_package_stats, get_package_stats_for_user, get_all_package_stats
from app.markdown import render_markdown
from app.models import Tag, PackageState, PackageType, Package, db, PackageRelease, Permission, \
	MinetestRelease, APIToken, PackageScreenshot, License, ContentWarning, User, PackageReview, Thread, Collection, \
	PackageAlias, Language, PackageDailyStats
from app.querybuilder import QueryBuilder
from app.utils import is_package_page, get_int_or_abort, url_set_query, abs_url, is_yes, get_request_date, cached, \
	cors_allowed
from app.utils.minetest_hypertext import html_to_minetest, package_info_as_hypertext, package_reviews_as_hypertext
from . import bp
from .auth import is_api_authd
from .support import error, api_create_vcs_release, api_create_zip_release, api_create_screenshot, \
	api_order_screenshots, api_edit_package, api_set_cover_image
from ...rediscache import make_view_key, set_temp_key, has_key


@bp.route("/api/packages/")
@cors_allowed
@cached(300)
def packages():
	allowed_languages = set([x[0] for x in db.session.query(Language.id).all()])
	lang = request.accept_languages.best_match(allowed_languages)

	qb = QueryBuilder(request.args, lang=lang)
	query = qb.build_package_query()

	fmt = request.args.get("fmt")
	if fmt == "keys":
		return jsonify([pkg.as_key_dict() for pkg in query.all()])

	include_vcs = fmt == "vcs"
	pkgs = qb.convert_to_dictionary(query.all(), include_vcs)
	if "engine_version" in request.args or "protocol_version" in request.args:
		pkgs = [pkg for pkg in pkgs if pkg.get("release")]

	# Promote featured packages
	if "sort" not in request.args and \
			"order" not in request.args and \
			"q" not in request.args and \
			"limit" not in request.args:
		featured_lut = set()
		featured = qb.convert_to_dictionary(query.filter(
			Package.collections.any(and_(Collection.name == "featured", Collection.author.has(username="ContentDB")))).all(),
			include_vcs)
		for pkg in featured:
			featured_lut.add(f"{pkg['author']}/{pkg['name']}")
			pkg["short_description"] = gettext("Featured") + ". " + pkg["short_description"]
			pkg["featured"] = True

		not_featured = [pkg for pkg in pkgs if f"{pkg['author']}/{pkg['name']}" not in featured_lut]
		pkgs = featured + not_featured

	resp = jsonify(pkgs)
	resp.vary = "Accept-Language"
	return resp


@bp.route("/api/packages/<author>/<name>/")
@is_package_page
@cors_allowed
def package_view(package):
	allowed_languages = set([x[0] for x in db.session.query(Language.id).all()])
	lang = request.accept_languages.best_match(allowed_languages)

	data = package.as_dict(current_app.config["BASE_URL"], lang=lang)
	resp = jsonify(data)
	resp.vary = "Accept-Language"
	return resp


@bp.route("/api/packages/<author>/<name>/for-client/")
@is_package_page
@cors_allowed
def package_view_client(package: Package):
	ip = request.headers.get("X-Forwarded-For") or request.remote_addr
	if ip is not None and (request.headers.get("User-Agent") or "").startswith("Minetest"):
		key = make_view_key(ip, package)
		if not has_key(key):
			set_temp_key(key, "true")
			PackageDailyStats.notify_view(package)
			db.session.commit()

	protocol_version = request.args.get("protocol_version")
	engine_version = request.args.get("engine_version")
	if protocol_version or engine_version:
		version = MinetestRelease.get(engine_version, get_int_or_abort(protocol_version))
	else:
		version = None

	allowed_languages = set([x[0] for x in db.session.query(Language.id).all()])
	lang = request.accept_languages.best_match(allowed_languages)

	data = package.as_dict(current_app.config["BASE_URL"], version, lang=lang, screenshots_dict=True)

	formspec_version = get_int_or_abort(request.args["formspec_version"])
	include_images = is_yes(request.args.get("include_images", "true"))
	page_url = package.get_url("packages.view", absolute=True)
	if data["long_description"] is not None:
		html = render_markdown(data["long_description"])
		data["long_description"] = html_to_minetest(html, page_url, formspec_version, include_images)

	data["info_hypertext"] = package_info_as_hypertext(package, formspec_version)

	data["download_size"] = package.get_download_release(version).file_size

	data["reviews"] = {
		"positive": package.reviews.filter(PackageReview.rating > 3).count(),
		"neutral": package.reviews.filter(PackageReview.rating == 3).count(),
		"negative": package.reviews.filter(PackageReview.rating < 3).count(),
	}

	resp = jsonify(data)
	resp.vary = "Accept-Language"
	return resp


@bp.route("/api/packages/<author>/<name>/for-client/reviews/")
@is_package_page
@cors_allowed
def package_view_client_reviews(package: Package):
	formspec_version = get_int_or_abort(request.args["formspec_version"])
	data = package_reviews_as_hypertext(package, formspec_version)

	resp = jsonify(data)
	resp.vary = "Accept-Language"
	return resp


@bp.route("/api/packages/<author>/<name>/hypertext/")
@is_package_page
@cors_allowed
def package_hypertext(package):
	formspec_version = get_int_or_abort(request.args["formspec_version"])
	include_images = is_yes(request.args.get("include_images", "true"))
	html = render_markdown(package.desc if package.desc else "")
	page_url = package.get_url("packages.view", absolute=True)
	return jsonify(html_to_minetest(html, page_url, formspec_version, include_images))


@bp.route("/api/packages/<author>/<name>/", methods=["PUT"])
@csrf.exempt
@is_package_page
@is_api_authd
@cors_allowed
def edit_package(token, package):
	if not token:
		error(401, "Authentication needed")

	return api_edit_package(token, package, request.json)


def resolve_package_deps(out, package, only_hard, depth=1):
	id_ = package.get_id()
	if id_ in out:
		return

	ret = []
	out[id_] = ret

	if package.type != PackageType.MOD:
		return

	for dep in package.dependencies:
		if only_hard and dep.optional:
			continue

		if dep.package:
			name = dep.package.name
			fulfilled_by = [ dep.package.get_id() ]
			resolve_package_deps(out, dep.package, only_hard, depth)

		elif dep.meta_package:
			name = dep.meta_package.name
			fulfilled_by = [ pkg.get_id() for pkg in dep.meta_package.packages if pkg.state == PackageState.APPROVED]

			if depth == 1 and not dep.optional:
				most_likely = next((pkg for pkg in dep.meta_package.packages \
						if pkg.type == PackageType.MOD and pkg.state == PackageState.APPROVED), None)
				if most_likely:
					resolve_package_deps(out, most_likely, only_hard, depth + 1)

		else:
			raise Exception("Malformed dependency")

		ret.append({
			"name": name,
			"is_optional": dep.optional,
			"packages": fulfilled_by
		})


@bp.route("/api/packages/<author>/<name>/dependencies/")
@is_package_page
@cors_allowed
@cached(300)
def package_dependencies(package):
	only_hard = request.args.get("only_hard")

	out = {}
	resolve_package_deps(out, package, only_hard)

	return jsonify(out)


@bp.route("/api/topics/")
@cors_allowed
def topics():
	qb = QueryBuilder(request.args)
	query = qb.build_topic_query(show_added=True)
	return jsonify([t.as_dict() for t in query.all()])


@bp.route("/api/whoami/")
@is_api_authd
@cors_allowed
def whoami(token):
	if token is None:
		return jsonify({ "is_authenticated": False, "username": None })
	else:
		return jsonify({ "is_authenticated": True, "username": token.owner.username })


@bp.route("/api/delete-token/", methods=["DELETE"])
@csrf.exempt
@is_api_authd
@cors_allowed
def api_delete_token(token):
	if token is None:
		error(404, "Token not found")

	db.session.delete(token)
	db.session.commit()

	return jsonify({"success": True})


@bp.route("/api/markdown/", methods=["POST"])
@csrf.exempt
def markdown():
	return render_markdown(request.data.decode("utf-8"))


@bp.route("/api/releases/")
@cors_allowed
def list_all_releases():
	query = PackageRelease.query.filter_by(approved=True) \
			.filter(PackageRelease.package.has(state=PackageState.APPROVED)) \
			.order_by(db.desc(PackageRelease.created_at))

	if "author" in request.args:
		author = User.query.filter_by(username=request.args["author"]).first()
		if author is None:
			error(404, "Author not found")
		query = query.filter(PackageRelease.package.has(author=author))

	if "maintainer" in request.args:
		maintainer = User.query.filter_by(username=request.args["maintainer"]).first()
		if maintainer is None:
			error(404, "Maintainer not found")
		query = query.join(Package)
		query = query.filter(Package.maintainers.contains(maintainer))

	return jsonify([ rel.as_long_dict() for rel in query.limit(30).all() ])


@bp.route("/api/packages/<author>/<name>/releases/")
@is_package_page
@cors_allowed
def list_releases(package):
	return jsonify([ rel.as_dict() for rel in package.releases.all() ])


@bp.route("/api/packages/<author>/<name>/releases/new/", methods=["POST"])
@csrf.exempt
@is_package_page
@is_api_authd
@cors_allowed
def create_release(token, package):
	if not token:
		error(401, "Authentication needed")

	if not package.check_perm(token.owner, Permission.APPROVE_RELEASE):
		error(403, "You do not have the permission to approve releases")

	if request.headers.get("Content-Type") == "application/json":
		data = request.json
	else:
		data = request.form

	if not ("title" in data or "name" in data):
		error(400, "name is required in the POST data")

	name = data.get("name")
	title = data.get("title") or name
	name = name or title

	if data.get("method") == "git":
		for option in ["method", "ref"]:
			if option not in data:
				error(400, option + " is required in the POST data")

		return api_create_vcs_release(token, package, name, title, data.get("release_notes"), data["ref"])

	elif request.files:
		file = request.files.get("file")
		if file is None:
			error(400, "Missing 'file' in multipart body")

		commit_hash = data.get("commit")

		return api_create_zip_release(token, package,  name, title, data.get("release_notes"), file, None, None, "API", commit_hash)

	else:
		error(400, "Unknown release-creation method. Specify the method or provide a file.")


@bp.route("/api/packages/<author>/<name>/releases/<int:id>/")
@is_package_page
@cors_allowed
def release_view(package: Package, id: int):
	release = PackageRelease.query.get(id)
	if release is None or release.package != package:
		error(404, "Release not found")

	return jsonify(release.as_dict())


@bp.route("/api/packages/<author>/<name>/releases/<int:id>/", methods=["DELETE"])
@csrf.exempt
@is_package_page
@is_api_authd
@cors_allowed
def delete_release(token: APIToken, package: Package, id: int):
	release = PackageRelease.query.get(id)
	if release is None or release.package != package:
		error(404, "Release not found")

	if not token:
		error(401, "Authentication needed")

	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	if not release.check_perm(token.owner, Permission.DELETE_RELEASE):
		error(403, "Unable to delete the release, make sure there's a newer release available")

	db.session.delete(release)
	db.session.commit()

	if release.file_path and os.path.isfile(release.file_path):
		os.remove(release.file_path)

	return jsonify({"success": True})


@bp.route("/api/packages/<author>/<name>/screenshots/")
@is_package_page
@cors_allowed
def list_screenshots(package):
	screenshots = package.screenshots.all()
	return jsonify([ss.as_dict(current_app.config["BASE_URL"]) for ss in screenshots])


@bp.route("/api/packages/<author>/<name>/screenshots/new/", methods=["POST"])
@csrf.exempt
@is_package_page
@is_api_authd
@cors_allowed
def create_screenshot(token: APIToken, package: Package):
	if not token:
		error(401, "Authentication needed")

	if not package.check_perm(token.owner, Permission.ADD_SCREENSHOTS):
		error(403, "You do not have the permission to create screenshots")

	data = request.form
	if "title" not in data:
		error(400, "Title is required in the POST data")

	file = request.files.get("file")
	if file is None:
		error(400, "Missing 'file' in multipart body")

	return api_create_screenshot(token, package, data["title"], file, is_yes(data.get("is_cover_image")))


@bp.route("/api/packages/<author>/<name>/screenshots/<int:id>/")
@is_package_page
@cors_allowed
def screenshot(package, id):
	ss = PackageScreenshot.query.get(id)
	if ss is None or ss.package != package:
		error(404, "Screenshot not found")

	return jsonify(ss.as_dict(current_app.config["BASE_URL"]))


@bp.route("/api/packages/<author>/<name>/screenshots/<int:id>/", methods=["DELETE"])
@csrf.exempt
@is_package_page
@is_api_authd
@cors_allowed
def delete_screenshot(token: APIToken, package: Package, id: int):
	ss = PackageScreenshot.query.get(id)
	if ss is None or ss.package != package:
		error(404, "Screenshot not found")

	if not token:
		error(401, "Authentication needed")

	if not package.check_perm(token.owner, Permission.ADD_SCREENSHOTS):
		error(403, "You do not have the permission to delete screenshots")

	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	if package.cover_image == ss:
		package.cover_image = None
		db.session.merge(package)

	db.session.delete(ss)
	db.session.commit()

	os.remove(ss.file_path)

	return jsonify({ "success": True })


@bp.route("/api/packages/<author>/<name>/screenshots/order/", methods=["POST"])
@csrf.exempt
@is_package_page
@is_api_authd
@cors_allowed
def order_screenshots(token: APIToken, package: Package):
	if not token:
		error(401, "Authentication needed")

	if not package.check_perm(token.owner, Permission.ADD_SCREENSHOTS):
		error(403, "You do not have the permission to change screenshots")

	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	json = request.json
	if json is None or not isinstance(json, list):
		error(400, "Expected order body to be array")

	return api_order_screenshots(token, package, request.json)


@bp.route("/api/packages/<author>/<name>/screenshots/cover-image/", methods=["POST"])
@csrf.exempt
@is_package_page
@is_api_authd
@cors_allowed
def set_cover_image(token: APIToken, package: Package):
	if not token:
		error(401, "Authentication needed")

	if not package.check_perm(token.owner, Permission.ADD_SCREENSHOTS):
		error(403, "You do not have the permission to change screenshots")

	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	json = request.json
	if json is None or not isinstance(json, dict) or "cover_image" not in json:
		error(400, "Expected body to be an object with cover_image as a key")

	return api_set_cover_image(token, package, request.json["cover_image"])


@bp.route("/api/packages/<author>/<name>/reviews/")
@is_package_page
@cors_allowed
def list_reviews(package):
	reviews = package.reviews
	return jsonify([review.as_dict() for review in reviews])


@bp.route("/api/reviews/")
@cors_allowed
def list_all_reviews():
	page = get_int_or_abort(request.args.get("page"), 1)
	num = min(get_int_or_abort(request.args.get("n"), 100), 200)

	query = PackageReview.query
	query = query.options(joinedload(PackageReview.author), joinedload(PackageReview.package))

	if "for_user" in request.args:
		query = query.filter(PackageReview.package.has(Package.author.has(username=request.args["for_user"])))

	if "author" in request.args:
		query = query.filter(PackageReview.author.has(User.username == request.args.get("author")))

	if "is_positive" in request.args:
		if is_yes(request.args.get("is_positive")):
			query = query.filter(PackageReview.rating > 3)
		else:
			query = query.filter(PackageReview.rating <= 3)

	q = request.args.get("q")
	if q:
		query = query.filter(PackageReview.thread.has(Thread.title.ilike(f"%{q}%")))

	query = query.order_by(db.desc(PackageReview.created_at))

	pagination: flask_sqlalchemy.Pagination = query.paginate(page=page, per_page=num)
	return jsonify({
		"page": pagination.page,
		"per_page": pagination.per_page,
		"page_count": math.ceil(pagination.total / pagination.per_page),
		"total": pagination.total,
		"urls": {
			"previous": abs_url(url_set_query(page=page - 1)) if pagination.has_prev else None,
			"next": abs_url(url_set_query(page=page + 1)) if pagination.has_next else None,
		},
		"items": [review.as_dict(True) for review in pagination.items],
	})


@bp.route("/api/packages/<author>/<name>/stats/")
@is_package_page
@cors_allowed
@cached(300)
def package_stats(package: Package):
	start = get_request_date("start")
	end = get_request_date("end")
	return jsonify(get_package_stats(package, start, end))


@bp.route("/api/package_stats/")
@cors_allowed
@cached(900)
def all_package_stats():
	return jsonify(get_all_package_stats())


@bp.route("/api/scores/")
@cors_allowed
@cached(900)
def package_scores():
	qb = QueryBuilder(request.args)
	query = qb.build_package_query()

	pkgs = [package.as_score_dict() for package in query.all()]
	return jsonify(pkgs)


@bp.route("/api/tags/")
@cors_allowed
@cached(60*60)
def tags():
	return jsonify([tag.as_dict() for tag in Tag.query.order_by(db.asc(Tag.name)).all()])


@bp.route("/api/content_warnings/")
@cors_allowed
@cached(60*60)
def content_warnings():
	return jsonify([warning.as_dict() for warning in ContentWarning.query.order_by(db.asc(ContentWarning.name)).all() ])


@bp.route("/api/licenses/")
@cors_allowed
@cached(60*60)
def licenses():
	all_licenses = License.query.order_by(db.asc(License.name)).all()
	return jsonify([{"name": license.name, "is_foss": license.is_foss} for license in all_licenses])


@bp.route("/api/homepage/")
@cors_allowed
@cached(300)
def homepage():
	query = Package.query.filter_by(state=PackageState.APPROVED)
	count = query.count()

	spotlight = query.filter(
			Package.collections.any(and_(Collection.name == "spotlight", Collection.author.has(username="ContentDB")))) \
		.order_by(func.random()).limit(6).all()
	new = query.order_by(db.desc(Package.approved_at)).limit(4).all()
	pop_mod = query.filter_by(type=PackageType.MOD).order_by(db.desc(Package.score)).limit(8).all()
	pop_gam = query.filter_by(type=PackageType.GAME).order_by(db.desc(Package.score)).limit(8).all()
	pop_txp = query.filter_by(type=PackageType.TXP).order_by(db.desc(Package.score)).limit(8).all()
	high_reviewed = query.order_by(db.desc(Package.score - Package.score_downloads)) \
			.filter(Package.reviews.any()).limit(4).all()

	updated = db.session.query(Package).select_from(PackageRelease).join(Package) \
			.filter_by(state=PackageState.APPROVED) \
			.order_by(db.desc(PackageRelease.created_at)) \
			.limit(20).all()
	updated = updated[:4]

	downloads_result = db.session.query(func.sum(Package.downloads)).one_or_none()
	downloads = 0 if not downloads_result or not downloads_result[0] else downloads_result[0]

	def map_packages(packages: List[Package]):
		return [pkg.as_short_dict(current_app.config["BASE_URL"]) for pkg in packages]

	return jsonify({
		"count": count,
		"downloads": downloads,
		"spotlight": map_packages(spotlight),
		"new": map_packages(new),
		"updated": map_packages(updated),
		"pop_mod": map_packages(pop_mod),
		"pop_txp": map_packages(pop_txp),
		"pop_game": map_packages(pop_gam),
		"high_reviewed": map_packages(high_reviewed)
	})


@bp.route("/api/minetest_versions/")
@cors_allowed
def versions():
	protocol_version = request.args.get("protocol_version")
	engine_version = request.args.get("engine_version")
	if protocol_version or engine_version:
		rel = MinetestRelease.get(engine_version, get_int_or_abort(protocol_version))
		if rel is None:
			error(404, "No releases found")

		return jsonify(rel.as_dict())

	return jsonify([rel.as_dict() \
			for rel in MinetestRelease.query.all() if rel.get_actual() is not None])


@bp.route("/api/languages/")
@cors_allowed
def languages():
	return jsonify([x.as_dict() for x in Language.query.all()])


@bp.route("/api/dependencies/")
@cors_allowed
def all_deps():
	qb = QueryBuilder(request.args)
	query = qb.build_package_query()

	def format_pkg(pkg: Package):
		return {
			"type": pkg.type.to_name(),
			"author": pkg.author.username,
			"name": pkg.name,
			"provides": [x.name for x in pkg.provides],
			"depends": [str(x) for x in pkg.dependencies if not x.optional],
			"optional_depends": [str(x) for x in pkg.dependencies if x.optional],
		}

	page = get_int_or_abort(request.args.get("page"), 1)
	num = min(get_int_or_abort(request.args.get("n"), 100), 300)
	pagination: flask_sqlalchemy.Pagination = query.paginate(page=page, per_page=num)
	return jsonify({
		"page": pagination.page,
		"per_page": pagination.per_page,
		"page_count": math.ceil(pagination.total / pagination.per_page),
		"total": pagination.total,
		"urls": {
			"previous": abs_url(url_set_query(page=page - 1)) if pagination.has_prev else None,
			"next": abs_url(url_set_query(page=page + 1)) if pagination.has_next else None,
		},
		"items": [format_pkg(pkg) for pkg in pagination.items],
	})


@bp.route("/api/users/<username>/")
@cors_allowed
def user_view(username: str):
	user = User.query.filter_by(username=username).first()
	if user is None:
		error(404, "User not found")

	return jsonify(user.get_dict())


@bp.route("/api/users/<username>/stats/")
@cors_allowed
@cached(300)
def user_stats(username: str):
	user = User.query.filter_by(username=username).first()
	if user is None:
		error(404, "User not found")

	start = get_request_date("start")
	end = get_request_date("end")
	return jsonify(get_package_stats_for_user(user, start, end))


@bp.route("/api/cdb_schema/")
@cors_allowed
@cached(60*60)
def json_schema():
	tags = Tag.query.all()
	warnings = ContentWarning.query.all()
	licenses = License.query.order_by(db.asc(License.name)).all()
	return jsonify({
		"title": "CDB Config",
		"description": "Package Configuration",
		"type": "object",
		"$defs": {
			"license": {
				"enum": [license.name for license in licenses],
				"enumDescriptions": [license.is_foss and "FOSS" or "NON-FOSS" for license in licenses]
			},
		},
		"properties": {
			"type": {
				"description": "Package Type",
				"enum": ["MOD", "GAME", "TXP"],
				"enumDescriptions": ["Mod", "Game", "Texture Pack"]
			},
			"title": {
				"description": "Human-readable title",
				"type": "string"
			},
			"name": {
				"description": "Technical name (needs permission if already approved).",
				"type": "string",
				"pattern": "^[a-z_]+$"
			},
			"short_description": {
				"description": "Package Short Description",
				"type": ["string", "null"]
			},
			"dev_state": {
				"description": "Development State",
				"enum": [
					"WIP",
					"BETA",
					"ACTIVELY_DEVELOPED",
					"MAINTENANCE_ONLY",
					"AS_IS",
					"DEPRECATED",
					"LOOKING_FOR_MAINTAINER"
				]
			},
			"tags": {
				"description": "Package Tags",
				"type": "array",
				"items": {
					"enum": [tag.name for tag in tags],
					"enumDescriptions": [tag.title for tag in tags]
				},
				"uniqueItems": True,
			},
			"content_warnings": {
				"description": "Package Content Warnings",
				"type": "array",
				"items": {
					"enum": [warning.name for warning in warnings],
					"enumDescriptions": [warning.title for warning in warnings]
				},
				"uniqueItems": True,
			},
			"license": {
				"description": "Package License",
				"$ref": "#/$defs/license"
			},
			"media_license": {
				"description": "Package Media License",
				"$ref": "#/$defs/license"
			},
			"long_description": {
				"description": "Package Long Description",
				"type": ["string", "null"]
			},
			"repo": {
				"description": "Git Repository URL",
				"type": "string",
				"format": "uri"
			},
			"website": {
				"description": "Website URL",
				"type": ["string", "null"],
				"format": "uri"
			},
			"issue_tracker": {
				"description": "Issue Tracker URL",
				"type": ["string", "null"],
				"format": "uri"
			},
			"forums": {
				"description": "Forum Topic ID",
				"type": ["integer", "null"],
				"minimum": 0
			},
			"video_url": {
				"description": "URL to a Video",
				"type": ["string", "null"],
				"format": "uri"
			},
			"donate_url": {
				"description": "URL to a donation page",
				"type": ["string", "null"],
				"format": "uri"
			},
			"translation_url": {
				"description": "URL to send users interested in translating your package",
				"type": ["string", "null"],
				"format": "uri"
			}
		},
	})


@bp.route("/api/hypertext/", methods=["POST"])
@csrf.exempt
@cors_allowed
def hypertext():
	formspec_version = get_int_or_abort(request.args["formspec_version"])
	include_images = is_yes(request.args.get("include_images", "true"))

	html = request.data.decode("utf-8")
	if request.content_type == "text/markdown":
		html = render_markdown(html)

	return jsonify(html_to_minetest(html, "", formspec_version, include_images))


@bp.route("/api/collections/")
@cors_allowed
def collection_list():
	if "author" in request.args:
		user = User.query.filter_by(username=request.args["author"]).one_or_404()
		query = user.collections
	else:
		query = Collection.query.order_by(db.asc(Collection.title))

	if "package" in request.args:
		id_ = request.args["package"]
		package = Package.get_by_key(id_)
		if package is None:
			error(404, f"Package {id_} not found")

		query = query.filter(Collection.packages.contains(package))

	collections = [x.as_short_dict() for x in query.all() if not x.private]
	return jsonify(collections)


@bp.route("/api/collections/<author>/<name>/")
@is_api_authd
@cors_allowed
def collection_view(token, author, name):
	user = token.owner if token else None

	collection = Collection.query \
		.filter(Collection.name == name, Collection.author.has(username=author)) \
		.one_or_404()

	if not collection.check_perm(user, Permission.VIEW_COLLECTION):
		error(404, "Collection not found")

	items = collection.items
	if not collection.check_perm(user, Permission.EDIT_COLLECTION):
		items = [x for x in items if x.package.check_perm(user, Permission.VIEW_PACKAGE)]

	ret = collection.as_dict()
	ret["items"] = [x.as_dict() for x in items]
	return jsonify(ret)


@bp.route("/api/updates/")
@cors_allowed
@cached(300)
def updates():
	protocol_version = get_int_or_abort(request.args.get("protocol_version"))
	minetest_version = request.args.get("engine_version")
	if protocol_version or minetest_version:
		version = MinetestRelease.get(minetest_version, protocol_version)
	else:
		version = None

	# Subquery to get the latest release for each package
	latest_release_query = (db.session.query(
		PackageRelease.package_id,
		func.max(PackageRelease.id).label('max_release_id'))
			.select_from(PackageRelease)
			.filter(PackageRelease.approved == True))

	if version:
		latest_release_query = (latest_release_query
			.filter(or_(PackageRelease.min_rel_id == None,
				PackageRelease.min_rel_id <= version.id))
			.filter(or_(PackageRelease.max_rel_id == None,
				PackageRelease.max_rel_id >= version.id)))

	latest_release_subquery = (
		latest_release_query
		.group_by(PackageRelease.package_id)
		.subquery()
	)

	# Get package id and latest release
	query = (db.session.query(User.username, Package.name, latest_release_subquery.c.max_release_id)
		.select_from(Package)
		.join(User, Package.author)
		.join(latest_release_subquery, Package.id == latest_release_subquery.c.package_id)
		.filter(Package.state == PackageState.APPROVED)
		.all())

	ret = {}
	for author_username, package_name, release_id in query:
		ret[f"{author_username}/{package_name}"] = release_id

	# Get aliases
	aliases = (db.session.query(PackageAlias.author, PackageAlias.name, User.username, Package.name)
		.select_from(PackageAlias)
		.join(Package, PackageAlias.package)
		.join(User, Package.author)
		.filter(Package.state == PackageState.APPROVED)
		.all())

	for old_author, old_name, new_author, new_name in aliases:
		new_release = ret.get(f"{new_author}/{new_name}")
		if new_release is not None:
			ret[f"{old_author}/{old_name}"] = new_release

	return jsonify(ret)
