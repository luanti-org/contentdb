# ContentDB
# Copyright (C) 2018-21 rubenwardy
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

from typing import Optional
from flask import jsonify, abort, make_response, url_for, current_app

from app.logic.packages import do_edit_package
from app.logic.releases import LogicError, do_create_vcs_release, do_create_zip_release
from app.logic.screenshots import do_create_screenshot, do_order_screenshots, do_set_cover_image
from app.models import APIToken, Package, LuantiRelease, PackageScreenshot


def error(code: int, msg: str):
	abort(make_response(jsonify({ "success": False, "error": msg }), code))


# Catches LogicErrors and aborts with JSON error
def guard(f):
	def ret(*args, **kwargs):
		try:
			return f(*args, **kwargs)
		except LogicError as e:
			error(e.code, e.message)

	return ret


def api_create_vcs_release(token: APIToken, package: Package, name: str, title: Optional[str], release_notes: Optional[str], ref: str,
		min_v: LuantiRelease = None, max_v: LuantiRelease = None, reason="API"):
	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	reason += ", token=" + token.name

	rel = guard(do_create_vcs_release)(token.owner, package, name, title, release_notes, ref, min_v, max_v, reason)

	return jsonify({
		"success": True,
		"task": url_for("tasks.check", id=rel.task_id),
		"release": rel.as_dict()
	})


def api_create_zip_release(token: APIToken, package: Package, name: str, title: Optional[str], release_notes: Optional[str], file,
		min_v: LuantiRelease = None, max_v: LuantiRelease = None, reason="API", commit_hash: str = None):
	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	reason += ", token=" + token.name

	rel = guard(do_create_zip_release)(token.owner, package, name, title, release_notes, file, min_v, max_v, reason, commit_hash)

	return jsonify({
		"success": True,
		"task": url_for("tasks.check", id=rel.task_id),
		"release": rel.as_dict()
	})


def api_create_screenshot(token: APIToken, package: Package, title: str, file, is_cover_image: bool, reason="API"):
	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	reason += ", token=" + token.name

	ss : PackageScreenshot = guard(do_create_screenshot)(token.owner, package, title, file, is_cover_image, reason)

	return jsonify({
		"success": True,
		"screenshot": ss.as_dict()
	})


def api_order_screenshots(token: APIToken, package: Package, order: [any]):
	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	guard(do_order_screenshots)(token.owner, package, order)

	return jsonify({
		"success": True
	})


def api_set_cover_image(token: APIToken, package: Package, cover_image):
	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	guard(do_set_cover_image)(token.owner, package, cover_image)

	return jsonify({
		"success": True
	})


def api_edit_package(token: APIToken, package: Package, data: dict, reason: str = "API"):
	if not token.can_operate_on_package(package):
		error(403, "API token does not have access to the package")

	reason += ", token=" + token.name

	was_modified = guard(do_edit_package)(token.owner, package, False, False, data, reason)
	return jsonify({
		"success": True,
		"package": package.as_dict(current_app.config["BASE_URL"]),
		"was_modified": was_modified,
	})
