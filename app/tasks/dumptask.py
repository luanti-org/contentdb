# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from . import celery
from app import app
from app.models import User, Package, PackageState
import json, os, zipfile, datetime
from app.uploads import copy_to_uploads
from app.utils.files import get_temp_dir


@celery.task()
def create_database_dump():
	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	with get_temp_dir() as tmp_dir:
		tmp_path = os.path.join(tmp_dir, f"backup-{date}.zip")
		with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zipf:
			zipf.writestr("backup/index.json", json.dumps({ "created_at": datetime.datetime.utcnow().isoformat() }, indent=4))

			users = User.query.filter(User.packages.any(state=PackageState.APPROVED)).all()
			for user in users:
				str = json.dumps(user.get_dict(), indent=4)
				zipf.writestr(f"backup/{user.username}/index.json", str)

			packages = Package.query.filter_by(state=PackageState.APPROVED).all()
			for package in packages:
				str = json.dumps(package.as_dict(base_url=app.config["BASE_URL"]), indent=4)
				zipf.writestr(f"backup/{package.author.username}/{package.name}/index.json", str)

				releases = [release.as_dict() for release in package.releases]
				str = json.dumps(releases, indent=4)
				zipf.writestr(f"backup/{package.author.username}/{package.name}/releases.json", str)

		copy_to_uploads(tmp_path)
