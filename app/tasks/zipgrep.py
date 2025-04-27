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
import sys
from subprocess import Popen, PIPE, TimeoutExpired
from typing import Optional, List

from app.models import Package, PackageState, PackageRelease
from app.tasks import celery


@celery.task(bind=True)
def search_in_releases(self, query: str, file_filter: str, types: List[str]):
	pkg_query = Package.query.filter(Package.state == PackageState.APPROVED)
	if len(types) > 0:
		pkg_query = pkg_query.filter(Package.type.in_(types))

	packages = list(pkg_query.all())
	results = []

	total = len(packages)
	self.update_state(state="PROGRESS", meta={"current": 0, "total": total})

	while len(packages) > 0:
		package = packages.pop()
		release: Optional[PackageRelease] = package.get_download_release()
		if release:
			print(f"[Zipgrep] Checking {package.name}", file=sys.stderr)
			self.update_state(state="PROGRESS", meta={
				"current": total - len(packages),
				"total": total,
				"running": [package.as_key_dict()],
			})

			handle = Popen(["zipgrep", query, release.file_path, file_filter], stdout=PIPE, encoding="UTF-8")

			try:
				handle.wait(timeout=15)
			except TimeoutExpired:
				print(f"[Zipgrep] Timeout for {package.name}", file=sys.stderr)
				handle.kill()
				results.append({
					"package": package.as_key_dict(),
					"lines": "Error: timeout",
				})
				continue

			exit_code = handle.poll()
			if exit_code is None:
				print(f"[Zipgrep] Timeout for {package.name}", file=sys.stderr)
				handle.kill()
				results.append({
					"package": package.as_key_dict(),
					"lines": "Error: timeout",
				})
			elif exit_code == 0:
				print(f"[Zipgrep] Success for {package.name}", file=sys.stderr)
				results.append({
					"package": package.as_key_dict(),
					"lines": handle.stdout.read(),
				})
			elif exit_code != 1:
				print(f"[Zipgrep] Error {exit_code} for {package.name}", file=sys.stderr)
				results.append({
					"package": package.as_key_dict(),
					"lines": f"Error: exit {exit_code}",
				})

	return {
		"query": query,
		"matches": results,
	}
