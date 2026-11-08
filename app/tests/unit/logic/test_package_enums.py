# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest

from app.models import PackageDevState


@pytest.mark.parametrize("state", list(PackageDevState))
def test_dev_state_titles_match_values(state):
	"""
	Untranslated titles should match the enum values, so each state shows its own name.
	"""
	assert str(state.title) == state.value.replace("As-Is", "As-is")
