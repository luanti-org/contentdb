# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from datetime import datetime as dt
from urllib.parse import urlparse

from flask import request, has_request_context
from flask_babel import format_timedelta, gettext, get_locale
from flask_login import current_user
from markupsafe import Markup

from . import app, utils
from app.markdown import get_headings
from .models import Permission, Package, PackageState, PackageRelease, ReleaseState
from .utils import abs_url_for, url_set_query, url_set_anchor, url_current
from .utils.luanti_hypertext import normalize_whitespace as do_normalize_whitespace


@app.context_processor
def inject_misc():
	hide_nonfree = False
	if has_request_context():
		hide_nonfree = request.cookies.get("hide_nonfree") == "1"
	return dict(debug=app.debug, hide_nonfree=hide_nonfree, locale=get_locale(),
			admin_contact_url=app.config["ADMIN_CONTACT_URL"],
			monitoring_url=app.config.get("MONITORING_URL"))


@app.context_processor
def inject_functions():
	check_global_perm = Permission.check_perm
	return dict(abs_url_for=abs_url_for, url_set_query=url_set_query, url_set_anchor=url_set_anchor,
			check_global_perm=check_global_perm, get_headings=get_headings, url_current=url_current)


@app.context_processor
def inject_todo():
	todo_list_count = None
	if current_user and current_user.is_authenticated and current_user.can_access_todo_list():
		todo_list_count = Package.query.filter_by(state=PackageState.READY_FOR_REVIEW).count()
		todo_list_count += PackageRelease.query.filter_by(state=ReleaseState.UNAPPROVED, task_id=None).count()

	return dict(todo_list_count=todo_list_count)


@app.template_filter()
def throw(err):
	raise Exception(err)


def persist_safe(ret, original):
	return Markup(ret) if isinstance(original, Markup) else ret


@app.template_filter()
def normalize_whitespace(str):
	return persist_safe(do_normalize_whitespace(str).strip(), str)


@app.template_filter()
def domain(url):
	return urlparse(url).netloc


@app.template_filter()
def date(value):
	return value.strftime("%Y-%m-%d")


@app.template_filter()
def full_datetime(value):
	return value.strftime("%Y-%m-%d %H:%M") + " UTC"


@app.template_filter()
def datetime(value):
	delta = dt.utcnow() - value
	if delta.days == 0:
		return gettext("%(delta)s ago", delta=format_timedelta(value))
	else:
		return full_datetime(value)


@app.template_filter()
def isodate(value):
	return value.strftime("%Y-%m-%d")


@app.template_filter()
def timedelta(value):
	return format_timedelta(value)


@app.template_filter()
def abs_url(url):
	return utils.abs_url(url)


@app.template_filter()
def limit(arr, num):
	return arr[:num]


@app.template_filter()
def last_it(it):
	value = None
	for x in it:
		value = x
	return value


@app.template_filter()
def flatten(list):
	ret = []
	for x in list:
		ret.extend(x)
	return ret
