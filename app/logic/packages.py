# ContentDB
# Copyright (C) 2021 rubenwardy
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

import json
import re
import typing

import validators
from flask_babel import lazy_gettext, LazyString

from app.logic.LogicError import LogicError
from app.models import User, Package, PackageType, MetaPackage, Tag, ContentWarning, db, Permission, AuditSeverity, \
	License, PackageDevState, PackageState
from app.utils import add_audit_log, has_blocked_domains, diff_dictionaries, describe_difference, normalize_line_endings
from app.utils.url import clean_youtube_url


def check(cond: bool, msg: typing.Union[str, LazyString]):
	if not cond:
		raise LogicError(400, msg)


def get_license(name):
	if type(name) == License:
		return name

	license = License.query.filter(License.name.ilike(name)).first()
	if license is None:
		raise LogicError(400, "Unknown license " + name)
	return license


name_re = re.compile("^[a-z0-9_]+$")

AnyType = "?"
ALLOWED_FIELDS = {
	"type": AnyType,
	"title": str,
	"name": str,
	"short_description": str,
	"short_desc": str,
	"dev_state": AnyType,
	"tags": list,
	"content_warnings": list,
	"license": AnyType,
	"media_license": AnyType,
	"long_description": str,
	"desc": str,
	"repo": str,
	"website": str,
	"issue_tracker": str,
	"issueTracker": str,
	"forums": int,
	"video_url": str,
	"donate_url": str,
	"translation_url": str,
}

NULLABLE = {
	"tags",
	"content_warnings",
	"repo",
	"website",
	"issue_tracker",
	"issueTracker",
	"forums",
	"video_url",
	"donate_url",
	"translation_url",
}

ALIASES = {
	"short_description": "short_desc",
	"issue_tracker": "issueTracker",
	"long_description": "desc"
}


def is_int(val):
	try:
		int(val)
		return True
	except ValueError:
		return False


def validate(data: dict):
	for key, value in data.items():
		if value is None:
			check(key in NULLABLE, f"{key} must not be null")
		else:
			typ = ALLOWED_FIELDS.get(key)
			check(typ is not None, f"{key} is not a known field")
			if typ != AnyType:
				check(isinstance(value, typ), f"{key} must be a " + typ.__name__)

	if "name" in data:
		name = data["name"]
		check(isinstance(name, str), "Name must be a string")
		check(bool(name_re.match(name)),
			lazy_gettext("Name can only contain lower case letters (a-z), digits (0-9), and underscores (_)"))

	for key in ["repo", "website", "issue_tracker", "issueTracker"]:
		value = data.get(key)
		if value is not None:
			check(value.startswith("http://") or value.startswith("https://"),
					f"{key} must start with http:// or https://")
			check(validators.url(value), f"{key} must be a valid URL")


def do_edit_package(user: User, package: Package, was_new: bool, was_web: bool, data: dict,
		reason: str = None) -> bool:
	if not package.check_perm(user, Permission.EDIT_PACKAGE):
		raise LogicError(403, lazy_gettext("You don't have permission to edit this package"))

	if "name" in data and package.name != data["name"] and \
			not package.check_perm(user, Permission.CHANGE_NAME):
		raise LogicError(403, lazy_gettext("You don't have permission to change the package name"))

	before_dict = None
	if not was_new:
		before_dict = package.as_dict("/")

	for alias, to in ALIASES.items():
		if alias in data:
			data[to] = data[alias]

	validate(data)

	for field in ["short_desc", "desc", "website", "issueTracker", "repo", "video_url", "donate_url", "translation_url"]:
		if field in data and has_blocked_domains(data[field], user.username,
					f"{field} of {package.get_id()}"):
			raise LogicError(403, lazy_gettext("Linking to blocked sites is not allowed"))

	if "type" in data:
		new_type = PackageType.coerce(data["type"])
		if new_type == package.type:
			pass
		elif package.state != PackageState.APPROVED:
			package.type = new_type
		else:
			raise LogicError(403, lazy_gettext("You cannot change package type once approved"))

	if "dev_state" in data:
		data["dev_state"] = PackageDevState.coerce(data["dev_state"])

	if "license" in data:
		data["license"] = get_license(data["license"])

	if "media_license" in data:
		data["media_license"] = get_license(data["media_license"])

	if "desc" in data:
		data["desc"] = normalize_line_endings(data["desc"])

	if "video_url" in data and data["video_url"] is not None:
		data["video_url"] = clean_youtube_url(data["video_url"]) or data["video_url"]
		if "dQw4w9WgXcQ" in data["video_url"]:
			raise LogicError(403, "Never gonna give you up / Never gonna let you down / Never gonna run around and desert you")

	for key in ["name", "title", "short_desc", "desc", "dev_state", "license", "media_license",
			"repo", "website", "issueTracker", "forums", "video_url", "donate_url", "translation_url"]:
		if key in data:
			setattr(package, key, data[key])

	if package.type == PackageType.TXP:
		package.license = package.media_license

	if was_new and package.type == PackageType.MOD:
		m = MetaPackage.GetOrCreate(package.name, {})
		package.provides.append(m)

	if "tags" in data:
		package.tags.clear()
		for tag_id in (data["tags"] or []):
			if is_int(tag_id):
				tag = Tag.query.get(tag_id)
			else:
				tag = Tag.query.filter_by(name=tag_id).first()
				if tag is None:
					raise LogicError(400, "Unknown tag: " + tag_id)

			package.tags.append(tag)

	if "content_warnings" in data:
		package.content_warnings.clear()
		for warning_id in (data["content_warnings"] or []):
			if is_int(warning_id):
				package.content_warnings.append(ContentWarning.query.get(warning_id))
			else:
				warning = ContentWarning.query.filter_by(name=warning_id).first()
				if warning is None:
					raise LogicError(400, "Unknown warning: " + warning_id)
				package.content_warnings.append(warning)

	was_modified = was_new
	if not was_new:
		after_dict = package.as_dict("/")
		diff = diff_dictionaries(before_dict, after_dict)
		was_modified = len(diff) > 0

		if reason is None:
			msg = "Edited {}".format(package.title)
		else:
			msg = "Edited {} ({})".format(package.title, reason)

		diff_desc = describe_difference(diff, 100 - len(msg) - 3) if diff else None
		if diff_desc:
			msg += " [" + diff_desc + "]"

		severity = AuditSeverity.NORMAL if user in package.maintainers else AuditSeverity.EDITOR
		add_audit_log(severity, user, msg, package.get_url("packages.view"), package, json.dumps(diff, indent=4))

	if was_modified:
		db.session.commit()

	return was_modified
