# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import render_template

from . import bp
from app.models import db, PackageUpdateConfig, Package, UserRank, PackageState
from app.utils import rank_required


@bp.route("/admin/update_config/")
@rank_required(UserRank.APPROVER)
def update_config():
	failing_packages = (db.session.query(Package)
			.select_from(PackageUpdateConfig)
			.filter(PackageUpdateConfig.task_id != None)
			.order_by(PackageUpdateConfig.last_checked_at.desc())
			.join(PackageUpdateConfig.package)
			.filter(Package.state == PackageState.APPROVED)
			.all())
	return render_template("admin/update_config.html", failing_packages=failing_packages)
