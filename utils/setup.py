# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2026 rubenwardy <rw@rubenwardy>

"""
Fills a new database with an admin user and static data like tags and licenses.
Run the migrations first, to create the tables.

Usage: python utils/setup.py [-t]

  -t  also add test users and packages

When run interactively, it asks for the admin's username and password. Otherwise, it uses the development
defaults, which are used by CI.
"""

import getpass
import inspect
import os
import sys
from typing import Callable


if "FLASK_CONFIG" not in os.environ:
	os.environ["FLASK_CONFIG"] = "../config.cfg"

# Allow finding the `app` module
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))  # type: ignore[arg-type]
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)


MIN_PASSWORD_LENGTH = 12


def prompt_admin(read_line: Callable[[str], str] = input,
		read_password: Callable[[str], str] = getpass.getpass) -> tuple[str, str]:
	from app.utils.user import is_username_valid

	while True:
		username = read_line("Admin username: ").strip()
		if is_username_valid(username):
			break
		print("Usernames must be at least 2 characters, using only letters, numbers, and . _ -")

	while True:
		password = read_password("Admin password: ")
		if len(password) < MIN_PASSWORD_LENGTH:
			print(f"Passwords must be at least {MIN_PASSWORD_LENGTH} characters")
		elif password != read_password("Confirm password: "):
			print("Passwords don't match")
		else:
			return username, password


def main(argv: list[str], interactive: bool) -> int:
	if any(x != "-t" for x in argv):
		print(__doc__.strip(), file=sys.stderr)
		return 2

	test_data = "-t" in argv

	from app import app
	from app.models import db, User, License
	from app.default_data import populate, populate_test_data, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD

	with app.app_context():
		if User.query.count() > 0 or License.query.count() > 0:
			print("The database already has data, so it has already been set up", file=sys.stderr)
			return 1

		if interactive:
			username, password = prompt_admin()
			link_accounts = False
		else:
			username, password = DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD
			link_accounts = True
			print(f"Not interactive, so creating the default admin {username} with the default password. "
					"Change it before using this instance publicly.")

		print("Filling database...")
		populate(db.session, username, password, link_accounts)
		if test_data:
			populate_test_data(db.session)
		db.session.commit()

		print(f"Created admin {username}" + (", and test data" if test_data else ""))

	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:], sys.stdin.isatty()))
