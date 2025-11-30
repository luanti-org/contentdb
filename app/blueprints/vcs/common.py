# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


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
