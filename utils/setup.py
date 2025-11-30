# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


import inspect
import os
import sys


if not "FLASK_CONFIG" in os.environ:
	os.environ["FLASK_CONFIG"] = "../config.cfg"

create_db = not (len(sys.argv) >= 2 and sys.argv[1].strip() == "-o")
test_data = len(sys.argv) >= 2 and sys.argv[1].strip() == "-t" or not create_db

# Allow finding the `app` module
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)

from app.models import db
from app.default_data import populate, populate_test_data

from app import app
with app.app_context():
	if create_db:
		print("Creating database tables...")
		db.create_all()

	print("Filling database...")

	populate(db.session)
	if test_data:
		populate_test_data(db.session)

	db.session.commit()
