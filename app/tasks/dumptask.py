# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

from . import celery
from app import app
from app.models import User, Package, PackageState, Dependency, db
import json
import os
import zipfile
import datetime
from app.uploads import copy_to_uploads
from app.utils.files import get_temp_dir


def get_dependency_names() -> dict[int, dict[str, list[str]]]:
	"""
	Returns the hard and optional dependencies of every package as mod names, keyed by package id.
	Loaded in one query, rather than one per package.
	"""
	names: dict[int, dict[str, set[str]]] = {}
	dependencies = Dependency.query \
		.options(db.joinedload(Dependency.meta_package), db.joinedload(Dependency.package)) \
		.filter(Dependency.depender_id.is_not(None)).all()
	for dep in dependencies:
		key = "optional_depends" if dep.optional else "depends"
		names.setdefault(dep.depender_id, {"depends": set(), "optional_depends": set()})[key].add(dep.get_name())

	return {
		package_id: {key: sorted(values) for key, values in deps.items()}
		for package_id, deps in names.items()
	}


@celery.task()
def create_database_dump():
	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	with get_temp_dir() as tmp_dir:
		tmp_path = os.path.join(tmp_dir, f"backup-{date}.zip")
		with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zipf:
			zipf.writestr("backup/index.json", json.dumps({ "created_at": datetime.datetime.utcnow().isoformat() }, indent=4))

			users = User.query.filter(User.packages.any(state=PackageState.APPROVED)).all()
			for user in users:
				content = json.dumps(user.get_dict(), indent=4)
				zipf.writestr(f"backup/{user.username}/index.json", content)

			dependency_names = get_dependency_names()
			no_dependencies: dict[str, list[str]] = {"depends": [], "optional_depends": []}

			packages = Package.query.filter_by(state=PackageState.APPROVED).all()
			for package in packages:
				# as_dict already includes `provides`
				data = package.as_dict(base_url=app.config["BASE_URL"])
				data.update(dependency_names.get(package.id, no_dependencies))
				content = json.dumps(data, indent=4)
				zipf.writestr(f"backup/{package.author.username}/{package.name}/index.json", content)

				releases = [release.as_dict() for release in package.releases]
				content = json.dumps(releases, indent=4)
				zipf.writestr(f"backup/{package.author.username}/{package.name}/releases.json", content)

		copy_to_uploads(tmp_path, os.path.basename(tmp_path))
