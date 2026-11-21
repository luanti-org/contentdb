# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from app.blueprints.homepage.widgets.categories import FIRST_HUE, get_hues


def hue_distance(a: int, b: int) -> int:
	return min(abs(a - b), 360 - abs(a - b))


def test_hues_are_unique_and_neighbours_differ():
	assert get_hues(0) == []
	assert get_hues(1) == [FIRST_HUE]

	for count in range(2, 25):
		hues = get_hues(count)
		assert len(set(hues)) == count, count
		assert all(0 <= hue < 360 for hue in hues)
		# Neighbours are never next to each other on the colour wheel, when there's room for that
		min_gap = min(hue_distance(a, b) for a, b in zip(hues, hues[1:], strict=False))
		assert min_gap >= 360 // count, (count, hues)


def test_ten_hues():
	"""The ten categories from the category migration"""
	hues = get_hues(10)
	assert sorted(hues) == sorted((FIRST_HUE + i * 36) % 360 for i in range(10))
	assert min(hue_distance(a, b) for a, b in zip(hues, hues[1:], strict=False)) >= 90
