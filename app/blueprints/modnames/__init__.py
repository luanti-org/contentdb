# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import Blueprint, redirect, render_template, abort
from sqlalchemy import func
from app.models import MetaPackage, Package, db, Dependency, PackageState, ForumTopic

bp = Blueprint("modnames", __name__)


@bp.route("/metapackages/<path:path>")
def mp_redirect(path):
	return redirect("/modnames/" + path)


@bp.route("/modnames/")
def list_all():
	modnames = db.session.query(MetaPackage, func.count(Package.id)) \
			.select_from(MetaPackage).outerjoin(MetaPackage.packages) \
			.order_by(db.asc(MetaPackage.name)) \
			.group_by(MetaPackage.id).all()
	return render_template("modnames/list.html", modnames=modnames)


@bp.route("/modnames/<name>/")
def view(name):
	modname = MetaPackage.query.filter_by(name=name).first()
	if modname is None:
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

	similar_topics = ForumTopic.query \
		.filter_by(name=name) \
		.filter(~ db.exists().where(Package.forums == ForumTopic.topic_id)) \
		.order_by(db.asc(ForumTopic.name), db.asc(ForumTopic.title)) \
		.all()

	return render_template("modnames/view.html", modname=modname,
			dependers=dependers, optional_dependers=optional_dependers,
			similar_topics=similar_topics)
