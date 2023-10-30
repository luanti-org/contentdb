# ContentDB
# Copyright (C) 2023 rubenwardy
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

import re
import typing

from flask import Blueprint, request, redirect, render_template, flash, abort, url_for
from flask_babel import lazy_gettext, gettext
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, FieldList, HiddenField, TextAreaField
from wtforms.validators import InputRequired, Length, Optional, Regexp

from app.models import Collection, db, Package, Permission, CollectionPackage, User, UserRank, AuditSeverity
from app.utils import nonempty_or_none
from app.utils.models import is_package_page, add_audit_log, create_session

bp = Blueprint("collections", __name__)


regex_invalid_chars = re.compile("[^a-z0-9_]")


@bp.route("/collections/")
@bp.route("/collections/<author>/")
def list_all(author=None):
	if author:
		user = User.query.filter_by(username=author).one_or_404()
		query = user.collections
	else:
		user = None
		query = Collection.query.filter(Collection.items.any()).order_by(db.asc(Collection.title))

	if "package" in request.args:
		package = Package.get_by_key(request.args["package"])
		if package is None:
			abort(404)

		query = query.filter(Collection.packages.contains(package))

	collections = [x for x in query.all() if x.check_perm(current_user, Permission.VIEW_COLLECTION)]
	return render_template("collections/list.html",
		user=user, collections=collections,
		noindex=len(collections) == 0, canonical_url=request.base_url)


@bp.route("/collections/<author>/<name>/")
def view(author, name):
	collection = Collection.query \
		.filter(Collection.name == name, Collection.author.has(username=author)) \
		.one_or_404()

	if not collection.check_perm(current_user, Permission.VIEW_COLLECTION):
		abort(404)

	items = collection.items
	if collection.check_perm(current_user, Permission.EDIT_COLLECTION):
		items = [x for x in items if x.package.check_perm(current_user, Permission.VIEW_PACKAGE)]

	return render_template("collections/view.html", collection=collection, items=items, canonical_url=request.base_url)


class CollectionForm(FlaskForm):
	title = StringField(lazy_gettext("Title"), [InputRequired(), Length(3, 100)])
	name = StringField("URL", [Optional(), Length(1, 20), Regexp("^[a-z0-9_]", 0,
		"Lower case letters (a-z), digits (0-9), and underscores (_) only")])
	short_description = StringField(lazy_gettext("Short Description"), [Optional(), Length(0, 200)])
	long_description = TextAreaField(lazy_gettext("Page Content"), [Optional()], filters=[nonempty_or_none])
	private = BooleanField(lazy_gettext("Private"))
	descriptions = FieldList(
		StringField(lazy_gettext("Short Description"), [Optional(), Length(0, 500)], filters=[nonempty_or_none]),
		min_entries=0)
	package_ids = FieldList(HiddenField(), min_entries=0)
	package_removed = FieldList(HiddenField(), min_entries=0)
	order = HiddenField()
	submit = SubmitField(lazy_gettext("Save"))


@bp.route("/collections/new/", methods=["GET", "POST"])
@bp.route("/collections/<author>/<name>/edit/", methods=["GET", "POST"])
@login_required
def create_edit(author=None, name=None):
	collection: typing.Optional[Collection] = None
	if author is not None and name is not None:
		collection = Collection.query \
			.filter(Collection.name == name, Collection.author.has(username=author)) \
			.one_or_404()
		if not collection.check_perm(current_user, Permission.EDIT_COLLECTION):
			abort(403)
	elif "author" in request.args:
		author = request.args["author"]
		if author != current_user.username and not current_user.rank.at_least(UserRank.EDITOR):
			abort(403)

	if author is None:
		author = current_user
	else:
		author = User.query.filter_by(username=author).one()

	form = CollectionForm(formdata=request.form, obj=collection)

	initial_packages = []
	if "package" in request.args:
		for package_id in request.args.getlist("package"):
			package = Package.get_by_key(package_id)
			if package:
				initial_packages.append(package)

	if request.method == "GET":
		# HACK: fix bug in wtforms
		form.private.data = collection.private if collection else False
		if collection:
			for item in collection.items:
				form.descriptions.append_entry(item.description)
				form.package_ids.append_entry(item.package.get_id())
				form.package_removed.append_entry("0")
		else:
			form.name = None

	if form.validate_on_submit():
		ret = handle_create_edit(collection, form, initial_packages, author)
		if ret:
			return ret

	return render_template("collections/create_edit.html",
			collection=collection, form=form)


def handle_create_edit(collection: Collection, form: CollectionForm,
		initial_packages: typing.List[Package], author: User):

	severity = AuditSeverity.NORMAL if author == current_user else AuditSeverity.EDITOR
	name = form.name.data if collection else regex_invalid_chars.sub("", form.title.data.lower().replace(" ", "_"))

	if collection is None or name != collection.name:
		if Collection.query \
				.filter(Collection.name == name, Collection.author == author) \
				.count() > 0:
			flash(gettext("A collection with a similar title already exists"), "danger")
			return

		if Package.query \
				.filter(Package.name == name, Package.author == author) \
				.count() > 0:
			flash(gettext("Unable to create collection as a package with that name already exists"), "danger")
			return

	if collection is None:
		collection = Collection()
		collection.author = author
		form.populate_obj(collection)
		collection.name = name
		db.session.add(collection)

		for package in initial_packages:
			link = CollectionPackage()
			link.package = package
			link.collection = collection
			link.order = len(collection.items)
			db.session.add(link)

		add_audit_log(severity, current_user,
				f"Created collection {collection.author.username}/{collection.name}",
				collection.get_url("collections.view"), None)

	else:
		form.populate_obj(collection)
		collection.name = name

		link_lookup = {}
		for link in collection.items:
			link_lookup[link.package.get_id()] = link

		for i, package_id in enumerate(form.package_ids):
			link = link_lookup.get(package_id.data)
			to_delete = form.package_removed[i].data == "1"
			if link is None:
				if to_delete:
					continue

				package = Package.get_by_key(package_id.data)
				if package is None:
					abort(400)

				link = CollectionPackage()
				link.package = package
				link.collection = collection
				link.description = form.descriptions[i].data
				link_lookup[link.package.get_id()] = link
				db.session.add(link)
			elif to_delete:
				db.session.delete(link)
			else:
				link.description = form.descriptions[i].data

		for i, package_id in enumerate(form.order.data.split(",")):
			if package_id != "":
				link_lookup[package_id].order = i + 1

		add_audit_log(severity, current_user,
				f"Edited collection {collection.author.username}/{collection.name}",
				collection.get_url("collections.view"), None)

	db.session.commit()
	return redirect(collection.get_url("collections.view"))


@bp.route("/collections/<author>/<name>/delete/", methods=["GET", "POST"])
@login_required
def delete(author, name):
	collection = Collection.query \
		.filter(Collection.name == name, Collection.author.has(username=author)) \
		.one_or_404()
	if not collection.check_perm(current_user, Permission.EDIT_COLLECTION):
		abort(403)

	if request.method == "POST":
		add_audit_log(AuditSeverity.NORMAL, current_user,
				f"Deleted collection {collection.author.username}/{collection.name}",
				collection.get_url("collections.view"), None)

		db.session.delete(collection)
		db.session.commit()
		return redirect(url_for("collections.list_all", author=author))

	return render_template("collections/delete.html", collection=collection)


def toggle_package(collection: Collection, package: Package):
	severity = AuditSeverity.NORMAL if collection.author == current_user else AuditSeverity.EDITOR

	author = User.query.get(collection.author_id) if collection.author is None else collection.author

	if package in collection.packages:
		CollectionPackage.query \
			.filter(CollectionPackage.collection == collection, CollectionPackage.package == package) \
			.delete(synchronize_session=False)
		add_audit_log(severity, current_user,
				f"Removed {package.get_id()} from collection {author.username}/{collection.name}",
				collection.get_url("collections.view"), None)
		db.session.commit()
		return False
	else:
		link = CollectionPackage()
		link.package = package
		link.collection = collection
		link.order = len(collection.items)
		db.session.add(link)
		add_audit_log(severity, current_user,
				f"Added {package.get_id()} to collection {author.username}/{collection.name}",
				collection.get_url("collections.view"), None)
		db.session.commit()
		return True


def get_or_create_favorites(session):
	collection = Collection.query.filter(Collection.name == "favorites", Collection.author == current_user).first()
	if collection is None:
		is_new = True
		collection = Collection()
		collection.title = "Favorites"
		collection.name = "favorites"
		collection.short_description = "My favorites"
		collection.author_id = current_user.id
		session.add(collection)
	else:
		is_new = False

	return collection, is_new


@bp.route("/packages/<author>/<name>/add-to/", methods=["GET", "POST"])
@is_package_page
@login_required
def package_add(package):
	with create_session() as new_session:
		collection, is_new = get_or_create_favorites(new_session)
		if is_new:
			new_session.commit()

	if request.method == "POST":
		collection_id = request.form["collection"]
		collection = Collection.query.get(collection_id)
		if collection is None:
			abort(404)

		if not collection.check_perm(current_user, Permission.EDIT_COLLECTION):
			abort(403)

		if toggle_package(collection, package):
			flash(gettext("Added package to collection"), "success")
		else:
			flash(gettext("Removed package from collection"), "success")

		return redirect(package.get_url("collections.package_add"))

	collections = current_user.collections.all()
	if current_user.rank.at_least(UserRank.EDITOR) and current_user.username != "ContentDB":
		collections.extend(Collection.query.filter(Collection.author.has(username="ContentDB")).all())

	return render_template("collections/package_add_to.html", package=package, collections=collections)


@bp.route("/packages/<author>/<name>/favorite/", methods=["POST"])
@is_package_page
@login_required
def package_toggle_favorite(package):
	collection, _is_new = get_or_create_favorites(db.session)

	if toggle_package(collection, package):
		msg = gettext("Added package to favorites collection")
		if not collection.private:
			msg += " " + gettext("(Public, change from Profile > My Collections)")

		flash(msg, "success")
	else:
		flash(gettext("Removed package from favorites collection"), "success")

	return redirect(package.get_url("packages.view"))


@bp.route("/collections/<author>/<name>/clone/", methods=["POST"])
@login_required
def clone(author, name):
	old_collection: typing.Optional[Collection] = Collection.query \
		.filter(Collection.name == name, Collection.author.has(username=author)) \
		.one_or_404()

	index = 0
	new_name = name
	new_title = old_collection.title
	while True:
		if Collection.query \
				.filter(Collection.name == new_name, Collection.author == current_user) \
				.count() == 0:
			break

		index += 1
		new_name = f"{name}_{index}"
		new_title = f"{old_collection.title} ({index})"

	collection = Collection()
	collection.title = new_title
	collection.author = current_user
	collection.short_description = old_collection.short_description
	collection.name = new_name
	collection.private = True
	db.session.add(collection)

	for item in old_collection.items:
		new_item = CollectionPackage()
		new_item.package = item.package
		new_item.collection = collection
		new_item.description = item.description
		new_item.order = item.order
		db.session.add(new_item)

	add_audit_log(AuditSeverity.NORMAL, current_user,
			f"Created collection {collection.name} from {old_collection.author.username}/{old_collection.name} ",
			collection.get_url("collections.view"), None)

	db.session.commit()

	return redirect(collection.get_url("collections.view"))
