# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import Blueprint
from flask_babel import gettext

from app.models import User, Package, Permission, PackageType

bp = Blueprint("packages", __name__)


def get_package_tabs(user: User, package: Package):
	if package is None or not package.check_perm(user, Permission.EDIT_PACKAGE):
		return []

	retval = [
		{
			"id": "edit",
			"title": gettext("Edit Details"),
			"url": package.get_url("packages.create_edit")
		},
		{
			"id": "translation",
			"title": gettext("Translation"),
			"url": package.get_url("packages.translation")
		},
		{
			"id": "releases",
			"title": gettext("Releases"),
			"url": package.get_url("packages.list_releases")
		},
		{
			"id": "screenshots",
			"title": gettext("Screenshots"),
			"url": package.get_url("packages.screenshots")
		},
		{
			"id": "maintainers",
			"title": gettext("Maintainers"),
			"url": package.get_url("packages.edit_maintainers")
		},
		{
			"id": "audit",
			"title": gettext("Audit Log"),
			"url": package.get_url("packages.audit")
		},
		{
			"id": "stats",
			"title": gettext("Statistics"),
			"url": package.get_url("packages.statistics")
		},
		{
			"id": "share",
			"title": gettext("Share and Badges"),
			"url": package.get_url("packages.share")
		},
		{
			"id": "remove",
			"title": gettext("Remove / Unpublish"),
			"url": package.get_url("packages.remove")
		}
	]

	if package.type == PackageType.MOD or package.type == PackageType.TXP:
		retval.insert(2, {
			"id": "game_support",
			"title": gettext("Supported Games"),
			"url": package.get_url("packages.game_support")
		})

	return retval


from . import packages, advanced_search, screenshots, releases, reviews, game_hub
