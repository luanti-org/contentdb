# ContentDB
# Copyright (C) 2024  rubenwardy
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


from app.blueprints.api.support import error
from app.models import Package, APIToken, Permission, PackageState


def get_packages_for_vcs_and_token(token: APIToken, repo_url: str) -> list[Package]:
	repo_url = repo_url.replace("https://", "").replace("http://", "").lower()
	if token.package:
		packages = [token.package]
		if not token.package.check_perm(token.owner, Permission.APPROVE_RELEASE):
			return error(403, "You do not have the permission to approve releases")

		actual_repo_url: str = token.package.repo or ""
		if repo_url not in actual_repo_url.lower():
			return error(400, "Repo URL does not match the API token's package")
	else:
		# Get package
		packages = Package.query.filter(
			Package.repo.ilike("%{}%".format(repo_url)), Package.state != PackageState.DELETED).all()
		if len(packages) == 0:
			return error(400,
					"Could not find package, did you set the VCS repo in CDB correctly? Expected {}".format(repo_url))
		packages = [x for x in packages if x.check_perm(token.owner, Permission.APPROVE_RELEASE)]
		if len(packages) == 0:
			return error(403, "You do not have the permission to approve releases")

	return packages
