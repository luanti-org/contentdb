# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from unittest import mock

from app.models import ContentWarning


def test_content_warning_uses_content_warnings_context():
	"""utils/extract_translations.py extracts content warnings with the "content_warnings" context"""
	warning = ContentWarning("Violence", "Contains violence")

	with mock.patch("app.models.packages.pgettext", side_effect=lambda context, text: f"{context}:{text}"):
		assert warning.get_translated() == {
			"title": "content_warnings:Violence",
			"description": "content_warnings:Contains violence",
		}
