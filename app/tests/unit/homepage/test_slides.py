# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime

import pytest

from app import app
from app.models import DashboardWidgetSlide

NOW = datetime.datetime(2026, 11, 20, 12, 0)
HOUR = datetime.timedelta(hours=1)


@pytest.mark.parametrize("starts_at,ends_at,active", [
	(None, None, True),
	(NOW - HOUR, None, True),
	(NOW + HOUR, None, False),
	(None, NOW + HOUR, True),
	(None, NOW - HOUR, False),
	(NOW - HOUR, NOW + HOUR, True),
	(NOW, NOW + HOUR, True),
	(NOW - HOUR, NOW, False),
])
def test_slide_is_active(starts_at, ends_at, active):
	slide = DashboardWidgetSlide()
	slide.starts_at = starts_at
	slide.ends_at = ends_at
	assert slide.is_active(NOW) == active


def test_custom_slide():
	from app.blueprints.homepage.widgets.spotlight import Slide

	slide = DashboardWidgetSlide()
	slide.title = "Game Jam"
	slide.description = "Make a game"
	slide.label = "Competition"
	slide.url = "/gamejam/"
	slide.image_path = "/uploads/abc.png"

	with app.test_request_context("/"):
		result = Slide.from_custom(slide)

	assert result.title == "Game Jam"
	assert result.url == "/gamejam/"
	assert result.label == "Competition"
	assert result.author is None
	assert result.review_summary is None
	assert result.image_url and "abc" in result.image_url
