# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import json
from typing import Any

from flask_babel import lazy_gettext

from app.domain.DomainError import DomainError
from app.uploads import upload_file
from app.models import User, Package, PackageScreenshot, Permission, NotificationType, db, AuditSeverity
from app.utils.models import add_notification, add_audit_log, add_audit_log_on_package
from app.utils.image import get_image_size


def do_create_screenshot(user: User, package: Package, title: str, file, is_cover_image: bool, reason: str | None = None):
	thirty_minutes_ago = datetime.datetime.now() - datetime.timedelta(minutes=30)
	count = package.screenshots.filter(PackageScreenshot.created_at > thirty_minutes_ago).count()
	if count >= 20:
		raise DomainError(429, lazy_gettext("Too many requests, please wait before trying again"))

	uploaded_url, uploaded_path = upload_file(file, "image", lazy_gettext("a PNG, JPEG, or WebP image file"))

	counter = 1
	for screenshot in package.screenshots.all():
		screenshot.order = counter
		counter += 1

	ss = PackageScreenshot()
	ss.package  = package
	ss.title    = title or "Untitled"
	ss.upload_path = uploaded_url
	ss.approved = package.check_perm(user, Permission.APPROVE_SCREENSHOT)
	ss.order    = counter
	ss.width, ss.height = get_image_size(uploaded_path)

	if ss.is_too_small():
		raise DomainError(429,
				lazy_gettext("Screenshot is too small, it should be at least %(width)s by %(height)s pixels",
						width=PackageScreenshot.HARD_MIN_SIZE[0], height=PackageScreenshot.HARD_MIN_SIZE[1]))

	db.session.add(ss)

	if reason is None:
		msg = "Created screenshot {}".format(ss.title)
	else:
		msg = "Created screenshot {} ({})".format(ss.title, reason)

	add_notification(package.maintainers, user, NotificationType.PACKAGE_EDIT, msg, package.get_url("packages.view"), package)
	add_audit_log(AuditSeverity.NORMAL, user, msg, package.get_url("packages.view"), package)

	db.session.commit()

	if is_cover_image:
		package.cover_image = ss
		db.session.commit()

	return ss


def do_order_screenshots(user: User, package: Package, order: list[Any]):
	lookup = {}
	for screenshot in package.screenshots.all():
		lookup[screenshot.id] = screenshot

	old_order = {ss_id: ss.order for ss_id, ss in lookup.items()}

	# Look up every ID before changing anything, so that an invalid ID leaves the order unchanged
	ordered = []
	for ss_id in order:
		try:
			ordered.append(lookup[int(ss_id)])
		except KeyError:
			raise DomainError(400, "Unable to find screenshot with id={}".format(ss_id))
		except (ValueError, TypeError):
			raise DomainError(400, "Invalid id, not a number: {}".format(json.dumps(ss_id)))

	for counter, screenshot in enumerate(ordered, start=1):
		screenshot.order = counter

	if any(ss.order != old_order[ss_id] for ss_id, ss in lookup.items()):
		add_audit_log_on_package(user, "Reordered screenshots", package.get_url("packages.screenshots"), package)

	db.session.commit()


def do_set_cover_image(user: User, package: Package, cover_image):
	try:
		cover_image = int(cover_image)
	except (ValueError, TypeError):
		raise DomainError(400, "Invalid id, not a number: {}".format(json.dumps(cover_image)))

	for screenshot in package.screenshots.all():
		if screenshot.id == cover_image:
			if package.cover_image != screenshot:
				package.cover_image = screenshot

				add_audit_log_on_package(user, "Set cover image to {}".format(screenshot.title),
						package.get_url("packages.screenshots"), package)

			db.session.commit()
			return

	raise DomainError(400, "Unable to find screenshot")
