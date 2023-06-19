# ContentDB
# Copyright (C) 2018-21 rubenwardy
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

import datetime
import typing
from urllib.parse import urljoin, urlparse, urlunparse

import user_agents
from flask import request, abort, url_for
from flask_babel import LazyString, lazy_gettext
from werkzeug.datastructures import MultiDict

from app import app


def is_safe_url(target):
	ref_url = urlparse(request.host_url)
	test_url = urlparse(urljoin(request.host_url, target))
	return test_url.scheme in ('http', 'https') and \
		   ref_url.netloc == test_url.netloc


# These are given to Jinja in template_filters.py

def abs_url_for(endpoint: str, **kwargs):
	scheme = "https" if app.config["BASE_URL"][:5] == "https" else "http"
	return url_for(endpoint, _external=True, _scheme=scheme, **kwargs)


def abs_url(path):
	return urljoin(app.config["BASE_URL"], path)


def abs_url_samesite(path):
	base = urlparse(app.config["BASE_URL"])
	return urlunparse(base._replace(path=path))


def url_current(abs=False):
	if request.args is None or request.view_args is None:
		return None

	args = MultiDict(request.args)
	dargs = dict(args.lists())
	dargs.update(request.view_args)
	if abs:
		return abs_url_for(request.endpoint, **dargs)
	else:
		return url_for(request.endpoint, **dargs)


def url_clear_query():
	if request.endpoint is None:
		return None

	dargs = dict()
	if request.view_args:
		dargs.update(request.view_args)

	return url_for(request.endpoint, **dargs)


def url_set_anchor(anchor):
	args = MultiDict(request.args)
	dargs = dict(args.lists())
	dargs.update(request.view_args)
	return url_for(request.endpoint, **dargs) + "#" + anchor


def url_set_query(**kwargs):
	if request.endpoint is None:
		return None

	args = MultiDict(request.args)

	for key, value in kwargs.items():
		if key == "_add":
			for key2, value_to_add in value.items():
				values = set(args.getlist(key2))
				values.add(value_to_add)
				args.setlist(key2, list(values))
		elif key == "_remove":
			for key2, value_to_remove in value.items():
				values = set(args.getlist(key2))
				values.discard(value_to_remove)
				args.setlist(key2, list(values))
		else:
			args.setlist(key, [ value ])

	dargs = dict(args.lists())
	if request.view_args:
		dargs.update(request.view_args)

	return url_for(request.endpoint, **dargs)


def get_int_or_abort(v, default=None):
	if v is None:
		return default

	try:
		return int(v or default)
	except ValueError:
		abort(400)


def is_user_bot():
	user_agent = request.headers.get('User-Agent')
	if user_agent is None:
		return True

	user_agent = user_agents.parse(user_agent)
	return user_agent.is_bot


def get_request_date(key: str) -> typing.Optional[datetime.date]:
	val = request.args.get(key)
	if val is None:
		return None

	try:
		return datetime.datetime.strptime(val, "%Y-%m-%d").date()
	except ValueError:
		abort(400)


def get_daterange_options() -> typing.List[typing.Tuple[LazyString, str]]:
	now = datetime.datetime.utcnow().date()
	days7 = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).date()
	days30 = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).date()
	days90 = (datetime.datetime.utcnow() - datetime.timedelta(days=90)).date()
	year_start = datetime.date(now.year, 1, 1)
	last_year_start = datetime.date(now.year - 1, 1, 1)
	last_year_end = datetime.date(now.year - 1, 12, 31)

	return [
		(lazy_gettext("All time"), url_clear_query()),
		(lazy_gettext("Last 7 days"), url_set_query(start=days7.isoformat(), end=now.isoformat())),
		(lazy_gettext("Last 30 days"), url_set_query(start=days30.isoformat(), end=now.isoformat())),
		(lazy_gettext("Last 90 days"), url_set_query(start=days90.isoformat(), end=now.isoformat())),
		(lazy_gettext("Year to date"), url_set_query(start=year_start, end=now.isoformat())),
		(lazy_gettext("Last year"), url_set_query(start=last_year_start, end=last_year_end)),
	]
