# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from flask import render_template
from flask_babel import lazy_gettext, gettext
from flask_wtf import FlaskForm
from wtforms.fields.choices import SelectField, SelectMultipleField
from wtforms.fields.simple import StringField, BooleanField
from wtforms.validators import Optional
from wtforms_sqlalchemy.fields import QuerySelectMultipleField, QuerySelectField

from . import bp
from ...models import PackageType, Tag, db, ContentWarning, License, Language, LuantiRelease, Package, PackageState


def make_label(obj: Tag | ContentWarning):
	translated = obj.get_translated()
	if translated["description"]:
		return "{}: {}".format(translated["title"], translated["description"])
	else:
		return translated["title"]


def get_hide_choices():
	ret = [
		("android_default", gettext("Android Default")),
		("desktop_default", gettext("Desktop Default")),
		("nonfree", gettext("Non-free")),
		("wip", gettext("Work in Progress")),
		("deprecated", gettext("Deprecated")),
		("*", gettext("All content warnings")),
	]
	content_warnings = ContentWarning.query.order_by(db.asc(ContentWarning.name)).all()
	tags = Tag.query.order_by(db.asc(Tag.name)).all()
	ret += [(x.name, make_label(x)) for x in content_warnings + tags]
	return ret


class AdvancedSearchForm(FlaskForm):
	q = StringField(lazy_gettext("Query"), [Optional()])
	type = SelectMultipleField(lazy_gettext("Type"), [Optional()],
			choices=PackageType.choices(), coerce=PackageType.coerce)
	author = StringField(lazy_gettext("Author"), [Optional()])
	tag = QuerySelectMultipleField(lazy_gettext('Tags'),
			query_factory=lambda: Tag.query.order_by(db.asc(Tag.name)),
			get_pk=lambda a: a.name, get_label=make_label)
	flag = QuerySelectMultipleField(lazy_gettext('Content Warnings'),
			query_factory=lambda: ContentWarning.query.order_by(db.asc(ContentWarning.name)),
			get_pk=lambda a: a.name, get_label=make_label)
	license = QuerySelectMultipleField(lazy_gettext("License"), [Optional()],
			query_factory=lambda: License.query.order_by(db.asc(License.name)),
			allow_blank=True, blank_value="",
			get_pk=lambda a: a.name, get_label=lambda a: a.name)
	game = QuerySelectField(lazy_gettext("Supports Game"), [Optional()],
			query_factory=lambda: Package.query.filter(Package.type == PackageType.GAME, Package.state == PackageState.APPROVED).order_by(db.asc(Package.name)),
			allow_blank=True, blank_value="",
			get_pk=lambda a: f"{a.author.username}/{a.name}",
			get_label=lambda a: lazy_gettext("%(title)s by %(author)s", title=a.title, author=a.author.display_name))
	lang = QuerySelectField(lazy_gettext("Language"),
			query_factory=lambda: Language.query.order_by(db.asc(Language.title)),
			allow_blank=True, blank_value="",
			get_pk=lambda a: a.id, get_label=lambda a: a.title)
	hide = SelectMultipleField(lazy_gettext("Hide Tags and Content Warnings"), [Optional()])
	engine_version = QuerySelectField(lazy_gettext("Luanti Version"),
			query_factory=lambda: LuantiRelease.query.order_by(db.asc(LuantiRelease.id)),
			allow_blank=True, blank_value="",
			get_pk=lambda a: a.value, get_label=lambda a: a.name)
	sort = SelectField(lazy_gettext("Sort by"), [Optional()], choices=[
		("", ""),
		("name", lazy_gettext("Name")),
		("title", lazy_gettext("Title")),
		("score", lazy_gettext("Package score")),
		("reviews", lazy_gettext("Reviews")),
		("downloads", lazy_gettext("Downloads")),
		("created_at", lazy_gettext("Created At")),
		("approved_at", lazy_gettext("Approved At")),
		("last_release", lazy_gettext("Last Release")),
	])
	order = SelectField(lazy_gettext("Order"), [Optional()], choices=[
		("desc", lazy_gettext("Descending")),
		("asc", lazy_gettext("Ascending")),
	])
	random = BooleanField(lazy_gettext("Random order"))


@bp.route("/packages/advanced-search/")
def advanced_search():
	form = AdvancedSearchForm()
	form.hide.choices = get_hide_choices()
	return render_template("packages/advanced_search.html", form=form)
