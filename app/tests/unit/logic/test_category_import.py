# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import pytest

from app.domain.DomainError import DomainError
from app.domain.category_import import CategoryRow, parse_category_csv


def test_parse_category_csv():
	# With a byte order mark, as spreadsheet exports often have, and columns in another order and case
	content = "﻿MAIN CATEGORY,Game,Review,Second category\n" \
		"Puzzle, NodeCore ,Agreed,Survival Sandbox\n" \
		"Adventure & RPG,\"Lord, of the Test\",,\n"

	assert parse_category_csv(content.encode("utf-8")) == [
		CategoryRow(2, "NodeCore", "Puzzle", "Survival Sandbox", ""),
		CategoryRow(3, "Lord, of the Test", "Adventure & RPG", "", ""),
	]


def test_parse_category_csv_link_column():
	content = "Game,Main category,Link\nNodeCore,Puzzle,https://content.luanti.org/packages/Warr1024/nodecore/\n"
	rows = parse_category_csv(content.encode("utf-8"))
	assert rows[0].link == "https://content.luanti.org/packages/Warr1024/nodecore/"
	assert rows[0].second == ""


@pytest.mark.parametrize("content,error", [
	(b"Game,Second category\nNodeCore,Puzzle\n", "Missing columns: main category"),
	(b"", "Missing columns: game, main category"),
	("Game,Main category\nNodeCöre,Puzzle\n".encode("latin-1"), "The file must be a UTF-8 CSV file"),
])
def test_parse_category_csv_errors(content, error):
	with pytest.raises(DomainError) as e:
		parse_category_csv(content)
	assert e.value.message == error
