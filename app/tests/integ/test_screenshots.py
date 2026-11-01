# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import pytest

from app.domain.DomainError import DomainError
from app.domain.screenshots import do_order_screenshots
from app.models import db, User, Package, PackageScreenshot
from .utils import login, make_package
from .utils import client # noqa


def make_package_with_screenshots(count: int) -> Package:
	package = make_package("testmod", User.query.filter_by(username="rubenwardy").one())

	for i in range(count):
		ss = PackageScreenshot()
		ss.package = package
		ss.title = f"Screenshot {i}"
		ss.upload_path = f"/uploads/{i}.png"
		ss.approved = True
		ss.order = i + 1
		ss.width = 1920
		ss.height = 1080
		db.session.add(ss)

	db.session.commit()
	return package


def test_order_screenshots_invalid_id_changes_nothing(client):
	package = make_package_with_screenshots(2)
	first, second = package.screenshots.order_by(PackageScreenshot.order).all()

	# The valid ID comes first, so it would be applied before the invalid one raises
	with pytest.raises(DomainError):
		do_order_screenshots(package.author, package, [str(second.id), "invalid"])

	assert first.order == 1
	assert second.order == 2


def test_failed_reorder_saves_nothing(client):
	package = make_package_with_screenshots(2)
	first, second = package.screenshots.order_by(PackageScreenshot.order).all()
	first_id, second_id = first.id, second.id
	assert package.cover_image is None

	login(client, "rubenwardy", "tuckfrump")

	# The rest of the form is valid, but isn't saved when the order fails
	rv = client.post("/packages/rubenwardy/testmod/screenshots/", data=dict(
			order=f"{second_id},invalid", cover_image=str(first_id)), follow_redirects=True)
	assert b"Invalid id, not a number" in rv.data

	db.session.expire_all()
	assert PackageScreenshot.query.filter_by(id=first_id).one().order == 1
	assert PackageScreenshot.query.filter_by(id=second_id).one().order == 2
	assert Package.query.filter_by(name="testmod").one().cover_image is None
