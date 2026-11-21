# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime

import pytest

from app.domain.email_bounces import get_bounce_reason
from app.utils.scaleway_tem import format_datetime, parse_datetime


def test_format_datetime():
	assert format_datetime(datetime.datetime(2026, 10, 27, 12, 30, 5, 123)) == "2026-10-27T12:30:05Z"


@pytest.mark.parametrize("value, expected", [
	(None, None),
	("", None),
	("2026-10-27T12:30:05Z", datetime.datetime(2026, 10, 27, 12, 30, 5)),
	# The API may give nanoseconds
	("2026-10-27T12:30:05.123456789Z", datetime.datetime(2026, 10, 27, 12, 30, 5, 123456)),
	("2026-10-27T13:30:05+01:00", datetime.datetime(2026, 10, 27, 12, 30, 5)),
])
def test_parse_datetime(value, expected):
	assert parse_datetime(value) == expected


def tries(*codes):
	return [{"rank": i + 1, "code": code} for i, code in enumerate(codes)]


@pytest.mark.parametrize("email, expected", [
	({"flags": ["mailbox_not_found"], "last_tries": tries(550)}, "mailbox_not_found (550)"),
	# The most specific flag, and the code from the last try
	({"flags": ["hard_bounce", "soft_bounce", "mailbox_not_found"], "last_tries": tries(451, 550)},
		"mailbox_not_found (550)"),
	({"flags": ["hard_bounce"], "last_tries": list(reversed(tries(451, 554)))}, "hard_bounce (554)"),
	({"flags": ["blocklisted"], "last_tries": []}, "blocklisted"),
	({"flags": ["spam"]}, "spam"),
	# Soft failures don't stop sending
	({"flags": ["soft_bounce", "mailbox_full", "greylisted"], "last_tries": tries(452)}, None),
	({"flags": [], "last_tries": tries(500)}, None),
	({}, None),
])
def test_get_bounce_reason(email, expected):
	assert get_bounce_reason(email) == expected
