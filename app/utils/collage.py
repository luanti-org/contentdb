# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Renders a wall of package thumbnails tilted back in 3D, for category tiles on the homepage. Done on the server so the
homepage only needs one image per tile, rather than loading packages and many thumbnails.
"""

import math

from PIL import Image, ImageOps

# Packages are repeated to fill the wall, which is larger than the output so the tilted plane covers it
COLS = 7
ROWS = 7
CELL_SIZE = (300, 200)
BACKGROUND = (30, 30, 30)
OUTPUT_SIZE = (640, 360)

# Like the old CSS: rotateZ(-45deg), then rotateX(50deg), in perspective. Tuned by eye for OUTPUT_SIZE
ROTATE_Z = math.radians(-45)
ROTATE_X = math.radians(50)
PERSPECTIVE = 1400.0
# Width of the wall relative to the output, so the tilted plane covers it (checked by test_collage.py)
WALL_SCALE = 3.0


def _wall_size() -> tuple[int, int]:
	return COLS * CELL_SIZE[0], ROWS * CELL_SIZE[1]


def _cell_position(cell: int) -> tuple[int, int]:
	return (cell % COLS) * CELL_SIZE[0], (cell // COLS) * CELL_SIZE[1]


def _wall_to_output(x: float, y: float) -> tuple[float, float]:
	"""Where a point on the flat wall ends up in the output"""
	width, height = _wall_size()
	# Scaled so the wall is WALL_SCALE times the output's width
	scale = WALL_SCALE * OUTPUT_SIZE[0] / width
	px, py = _project((x - width / 2) * scale, (y - height / 2) * scale)
	return px + OUTPUT_SIZE[0] / 2, py + OUTPUT_SIZE[1] / 2


def visible_cells() -> set[int]:
	"""The cells that can be seen in the output, at least in part"""
	cells = set()
	for cell in range(COLS * ROWS):
		x, y = _cell_position(cell)
		corners = [_wall_to_output(x + dx, y + dy) for dx in (0, CELL_SIZE[0]) for dy in (0, CELL_SIZE[1])]
		xs = [p[0] for p in corners]
		ys = [p[1] for p in corners]
		if max(xs) > 0 and min(xs) < OUTPUT_SIZE[0] and max(ys) > 0 and min(ys) < OUTPUT_SIZE[1]:
			cells.add(cell)
	return cells


def visible_cell_count() -> int:
	"""How many images the collage can show without repeating any"""
	return len(visible_cells())


def _cells_by_visibility() -> list[int]:
	"""Visible cells first, nearest the output's centre first, then the hidden cells"""
	visible = visible_cells()

	def key(cell: int) -> tuple[bool, float]:
		x, y = _cell_position(cell)
		px, py = _wall_to_output(x + CELL_SIZE[0] / 2, y + CELL_SIZE[1] / 2)
		return cell not in visible, math.hypot(px - OUTPUT_SIZE[0] / 2, py - OUTPUT_SIZE[1] / 2)

	return sorted(range(COLS * ROWS), key=key)


def assign_images(image_count: int) -> list[int | None]:
	"""
	The index of the image for each cell. Images are given to the most visible cells first, so each is used once
	before any repeats, and there are only repeats when there are fewer images than visible cells.
	"""
	assignment: list[int | None] = [None] * (COLS * ROWS)
	if image_count > 0:
		for i, cell in enumerate(_cells_by_visibility()):
			assignment[cell] = i % image_count
	return assignment


def _flat_wall(images: list[Image.Image]) -> Image.Image:
	"""A COLS x ROWS grid of the images, with no gaps between them"""
	wall = Image.new("RGB", _wall_size(), BACKGROUND)
	cells = [ImageOps.fit(image.convert("RGB"), CELL_SIZE, Image.Resampling.BICUBIC) for image in images]
	for cell, index in enumerate(assign_images(len(cells))):
		if index is not None:
			wall.paste(cells[index], _cell_position(cell))
	return wall


def _project(x: float, y: float) -> tuple[float, float]:
	"""Projects a point on the wall, centred on the origin, to the output, centred on the origin"""
	x, y = x * math.cos(ROTATE_Z) - y * math.sin(ROTATE_Z), x * math.sin(ROTATE_Z) + y * math.cos(ROTATE_Z)
	y, z = y * math.cos(ROTATE_X), y * math.sin(ROTATE_X)
	# The top of the wall is further away, so it recedes into the distance
	factor = PERSPECTIVE / (PERSPECTIVE - z)
	return x * factor, y * factor


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
	"""Gaussian elimination, for the 8x8 system of a perspective transform"""
	n = len(vector)
	rows = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
	for col in range(n):
		pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
		rows[col], rows[pivot] = rows[pivot], rows[col]
		for r in range(n):
			if r != col:
				factor = rows[r][col] / rows[col][col]
				rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col], strict=True)]
	return [rows[i][n] / rows[i][i] for i in range(n)]


def _perspective_coefficients(output_points, input_points) -> list[float]:
	"""Coefficients for Image.transform's PERSPECTIVE, which maps output pixels to input pixels"""
	matrix = []
	vector = []
	for (x, y), (u, v) in zip(output_points, input_points, strict=True):
		matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
		matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
		vector += [u, v]
	return _solve(matrix, vector)


def render_collage(images: list[Image.Image]) -> Image.Image:
	wall = _flat_wall(images)
	width, height = wall.size
	corners = [(0, 0), (width, 0), (width, height), (0, height)]
	projected = [_wall_to_output(x, y) for x, y in corners]
	coefficients = _perspective_coefficients(projected, corners)
	return wall.transform(OUTPUT_SIZE, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC,
			fillcolor=BACKGROUND)
