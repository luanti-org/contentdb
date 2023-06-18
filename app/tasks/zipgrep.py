# ContentDB
# Copyright (C) 2022 rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import subprocess
from subprocess import Popen, PIPE
from typing import Optional

from app.models import Package, PackageState, PackageRelease
from app.tasks import celery


@celery.task()
def search_in_releases(query: str, file_filter: str):
	packages = list(Package.query.filter(Package.state == PackageState.APPROVED).all())
	running = []
	results = []

	while len(packages) > 0 or len(running) > 0:
		# Check running
		for i in range(len(running) - 1, -1, -1):
			package: Package = running[i][0]
			handle: subprocess.Popen[str] = running[i][1]
			exit_code = handle.poll()
			if exit_code is None:
				continue
			elif exit_code == 0:
				results.append({
					"package": package.as_key_dict(),
					"lines": handle.stdout.read(),
				})

			del running[i]

		# Create new
		while len(running) < 1 and len(packages) > 0:
			package = packages.pop()
			release: Optional[PackageRelease] = package.get_download_release()
			if release:
				handle = Popen(["zipgrep", query, release.file_path, file_filter], stdout=PIPE, encoding="UTF-8")
				running.append([package, handle])

		if len(running) > 0:
			running[0][1].wait()

	return {
		"query": query,
		"matches": results,
	}
