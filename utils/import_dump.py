# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Imports a database dump (/uploads/backup-YYYY-MM-DD.zip) into this instance. Run inside the app container, or use
utils/import_dump.sh from the host.

Usage: python utils/import_dump.py <path/to/backup.zip | -> [--dry-run]

`-` reads the zip from stdin. `--dry-run` shows what would be imported, without changing the database.
"""

import inspect
import os
import shutil
import sys
import tempfile


if "FLASK_CONFIG" not in os.environ:
	os.environ["FLASK_CONFIG"] = "../config.cfg"

# Allow finding the `app` module
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))  # type: ignore[arg-type]
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)


def main(argv: list[str]) -> int:
	args = [x for x in argv if x != "--dry-run"]
	dry_run = "--dry-run" in argv
	if len(args) != 1:
		print(__doc__.strip(), file=sys.stderr)
		return 2

	from app import app
	from app.models import db
	from app.domain.dump_import import import_dump, DumpImportError

	with tempfile.TemporaryDirectory() as tmp_dir:
		path = args[0]
		if path == "-":
			path = os.path.join(tmp_dir, "dump.zip")
			with open(path, "wb") as f:
				shutil.copyfileobj(sys.stdin.buffer, f)
		elif not os.path.isfile(path):
			print(f"No such file: {path}", file=sys.stderr)
			return 1

		with app.app_context():
			try:
				summary = import_dump(path)
			except DumpImportError as e:
				db.session.rollback()
				print(f"Import failed, nothing was changed: {e}", file=sys.stderr)
				return 1

			for warning in summary.warnings:
				print(f"Warning: {warning}")

			print(f"Users: {summary.users_created} created, {summary.users_existing} already existed")
			print(f"Packages: {summary.packages_created} created, {len(summary.packages_existing)} already existed")

			if dry_run:
				db.session.rollback()
				print("Dry run, nothing was changed")
			else:
				db.session.commit()
				print("Import complete")

	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
