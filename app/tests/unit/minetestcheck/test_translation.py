# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import os

import pytest

from app.tasks.luanticheck.translation import parse_tr


def test_parses_tr():
	dirname = os.path.dirname(__file__)
	filepath = os.path.join(dirname, "foo.bar.fr.tr")
	out = parse_tr(filepath)

	assert out.language == "fr"
	assert out.textdomain == "foo.bar"
	assert len(out.entries) == 5
	assert out.entries["Hello, World!"] == "Bonjour, Monde!"
	assert out.entries["Hello @1!"] == "@1, salut!"
	assert out.entries["Cats = cool"] == "Chats = cool"
	assert out.entries["A \n newline"] == "Une \nnouvelle ligne"
	assert out.entries["Maybe @\n@=@"] == "Peut être @\n@=@"


def test_parses_tr_error_on_missing_textdomain():
	dirname = os.path.dirname(__file__)
	filepath = os.path.join(dirname, "no_textdomain_comment.fr.tr")

	with pytest.raises(SyntaxError) as e:
		parse_tr(filepath)

	assert str(e.value) == "Missing `# textdomain: no_textdomain_comment` at the top of the file"


def test_parses_tr_error_on_textdomain_mismatch():
	dirname = os.path.dirname(__file__)
	filepath = os.path.join(dirname, "textdomain_mismatch.fr.tr")

	with pytest.raises(SyntaxError) as e:
		parse_tr(filepath)

	assert str(e.value) == "Line 1: The filename's textdomain (textdomain_mismatch) should match the comment (foobar)"


def test_parses_tr_error_on_missing_eq():
	dirname = os.path.dirname(__file__)
	filepath = os.path.join(dirname, "err_missing_eq.fr.tr")

	with pytest.raises(SyntaxError) as e:
		parse_tr(filepath)

	assert str(e.value) == "Line 4: Missing = in line"


def test_parses_tr_error_on_bad_escape():
	dirname = os.path.dirname(__file__)
	filepath = os.path.join(dirname, "bad_escape.fr.tr")

	with pytest.raises(SyntaxError) as e:
		parse_tr(filepath)

	assert str(e.value) == "Line 2: Unknown escape character: x"


def test_parses_tr_error_on_bad_args():
	dirname = os.path.dirname(__file__)
	filepath = os.path.join(dirname, "bad_args.fr.tr")

	with pytest.raises(SyntaxError) as e:
		parse_tr(filepath)

	assert "Line 2: Arguments out of order in source, found @5 and expected @2." in str(e.value)


def test_parses_tr_error_on_unknown_arg():
	dirname = os.path.dirname(__file__)
	filepath = os.path.join(dirname, "unknown_arg.fr.tr")

	with pytest.raises(SyntaxError) as e:
		parse_tr(filepath)

	assert str(e.value) == "Line 2: Unknown argument @2 in translated string"
