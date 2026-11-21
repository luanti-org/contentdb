# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import math

from PIL import Image

from app.utils.collage import BACKGROUND, OUTPUT_SIZE, assign_images, render_collage, visible_cell_count, \
	visible_cells


def test_render_collage_covers_output():
	images = [Image.new("RGB", (640, 360), colour) for colour in [(200, 0, 0), (0, 200, 0), (0, 0, 200)]]
	collage = render_collage(images)

	assert collage.size == OUTPUT_SIZE
	# The tilted wall reaches every corner, so there's no empty background showing at the edges
	width, height = OUTPUT_SIZE
	for x, y in [(2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3)]:
		assert collage.getpixel((x, y)) != BACKGROUND, (x, y)
	assert len(set(collage.getdata())) > 3


def test_render_collage_without_images():
	assert render_collage([]).size == OUTPUT_SIZE


def test_images_are_only_repeated_when_there_are_too_few():
	visible = visible_cells()
	assert 6 <= len(visible) == visible_cell_count() < len(assign_images(1))

	# Enough images: each visible cell has a different one
	assignment = assign_images(len(visible))
	assert sorted(assignment[cell] or 0 for cell in visible) == list(range(len(visible)))
	assert all(assignment[cell] is not None for cell in visible)

	# Too few: every image is used before any is repeated
	assignment = assign_images(3)
	assert [assignment[cell] for cell in visible].count(0) == math.ceil(len(visible) / 3)
	assert {assignment[cell] for cell in visible} == {0, 1, 2}
