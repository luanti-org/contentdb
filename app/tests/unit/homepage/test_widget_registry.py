# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from app.blueprints.homepage import WIDGETS
from app.models import DashboardWidgetType


def test_every_widget_type_is_registered():
	assert set(WIDGETS.keys()) == set(DashboardWidgetType)


def test_widget_templates_exist():
	from app import app

	for widget_type, widget_class in WIDGETS.items():
		assert app.jinja_env.get_template(widget_class.template), widget_type
