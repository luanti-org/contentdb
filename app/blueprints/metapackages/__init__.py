# ContentDB
# Copyright (C) 2018  rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


from flask import *
from sqlalchemy import func
from app.models import MetaPackage, Package, db, Dependency, PackageState, ForumTopic

bp = Blueprint("metapackages", __name__)


@bp.route("/metapackages/")
def list_all():
	mpackages = db.session.query(MetaPackage, func.count(Package.id)) \
			.select_from(MetaPackage).outerjoin(MetaPackage.packages) \
			.order_by(db.asc(MetaPackage.name)) \
			.group_by(MetaPackage.id).all()
	return render_template("metapackages/list.html", mpackages=mpackages)


@bp.route("/metapackages/<name>/")
def view(name):
	mpackage = MetaPackage.query.filter_by(name=name).first()
	if mpackage is None:
		abort(404)

	dependers = db.session.query(Package) \
		.select_from(MetaPackage) \
		.filter(MetaPackage.name==name) \
		.join(MetaPackage.dependencies) \
		.join(Dependency.depender) \
		.filter(Dependency.optional==False, Package.state==PackageState.APPROVED) \
		.all()

	optional_dependers = db.session.query(Package) \
		.select_from(MetaPackage) \
		.filter(MetaPackage.name==name) \
		.join(MetaPackage.dependencies) \
		.join(Dependency.depender) \
		.filter(Dependency.optional==True, Package.state==PackageState.APPROVED) \
		.all()

	similar_topics = None
	if mpackage.packages.filter_by(state=PackageState.APPROVED).count() == 0:
		similar_topics = ForumTopic.query \
				.filter_by(name=name) \
				.order_by(db.asc(ForumTopic.name), db.asc(ForumTopic.title)) \
				.all()

	return render_template("metapackages/view.html", mpackage=mpackage,
			dependers=dependers, optional_dependers=optional_dependers,
			similar_topics=similar_topics)
