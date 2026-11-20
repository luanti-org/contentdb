# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import os
import re

import sass

from app import app


def test_spotlight_carousel_is_styled():
	"""The carousel's height is limited by custom.scss, which must use the class the template has"""
	with open(os.path.join(app.root_path, "blueprints", "homepage", "widgets", "spotlight", "spotlight.html")) as f:
		template = f.read()
	match = re.search(r'class="(spotlight-carousel) carousel', template)
	assert match

	css = sass.compile(filename=os.path.join(app.root_path, "scss", "custom.scss"), output_style="compressed")
	assert re.search(r"\." + match.group(1) + r" \.carousel-item,\." + match.group(1) + r" \.ratio\{max-height:50vh\}", css)
