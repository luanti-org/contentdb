from flask import render_template

from . import bp
from app.models import PackageUpdateConfig, Package


@bp.route("/admin/update_config/")
def update_config():
	failing_packages = Package.query.filter(Package.update_config.has(PackageUpdateConfig.task_id != None)).all()
	return render_template("admin/update_config.html", failing_packages=failing_packages)
