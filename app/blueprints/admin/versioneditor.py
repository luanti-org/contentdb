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
from flask_wtf import FlaskForm
from wtforms import *
from wtforms.validators import *

from app.models import *
from app.utils import rank_required
from . import bp


@bp.route("/versions/")
@rank_required(UserRank.MODERATOR)
def version_list():
	return render_template("admin/versions/list.html", versions=MinetestRelease.query.order_by(db.asc(MinetestRelease.id)).all())

class VersionForm(FlaskForm):
	name	 = StringField("Name", [InputRequired(), Length(3,100)])
	protocol = IntegerField("Protocol")
	submit   = SubmitField("Save")

@bp.route("/versions/new/", methods=["GET", "POST"])
@bp.route("/versions/<name>/edit/", methods=["GET", "POST"])
@rank_required(UserRank.MODERATOR)
def create_edit_version(name=None):
	version = None
	if name is not None:
		version = MinetestRelease.query.filter_by(name=name).first()
		if version is None:
			abort(404)

	form = VersionForm(formdata=request.form, obj=version)
	if form.validate_on_submit():
		if version is None:
			version = MinetestRelease(form.name.data)
			db.session.add(version)
			flash("Created version " + form.name.data, "success")
		else:
			flash("Updated version " + form.name.data, "success")

		form.populate_obj(version)
		db.session.commit()
		return redirect(url_for("admin.version_list"))

	return render_template("admin/versions/edit.html", version=version, form=form)
