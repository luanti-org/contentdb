# ContentDB
# Copyright (C) 2018-21  rubenwardy
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
import os
import redis

from flask import redirect, url_for, render_template, flash, request, Flask, send_from_directory, make_response, render_template_string
from flask_babel import Babel, gettext
from flask_flatpages import FlatPages
from flask_github import GitHub
from flask_login import logout_user, current_user, LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect

from app.markdown import init_markdown, render_markdown

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration


if os.getenv("SENTRY_DSN"):
	def before_send(event, hint):
		from app.tasks import TaskError
		if "exc_info" in hint:
			exc_type, exc_value, tb = hint["exc_info"]
			if isinstance(exc_value, TaskError):
				return None
		return event

	environment = os.getenv("SENTRY_ENVIRONMENT")
	assert environment is not None
	sentry_sdk.init(
		dsn=os.getenv("SENTRY_DSN"),
		environment=environment,

		integrations=[FlaskIntegration()],
		# Set traces_sample_rate to 1.0 to capture 100%
		# of transactions for performance monitoring.
		traces_sample_rate=0.1,
		# Set profiles_sample_rate to 1.0 to profile 100%
		# of sampled transactions.
		# We recommend adjusting this value in production.
		profiles_sample_rate=0.1,

		before_send=before_send,
	)


app = Flask(__name__, static_folder="public/static")


def my_flatpage_renderer(text):
	# Render with jinja first
	prerendered_body = render_template_string(text)
	return render_markdown(prerendered_body, clean=False)


app.config["FLATPAGES_ROOT"] = "flatpages"
app.config["FLATPAGES_EXTENSION"] = ".md"
app.config["FLATPAGES_HTML_RENDERER"] = my_flatpage_renderer
app.config["WTF_CSRF_TIME_LIMIT"] = None

app.config["BABEL_TRANSLATION_DIRECTORIES"] = "../translations"
app.config["LANGUAGES"] = {
	"en": "English",
	"cs": "čeština",
	"de": "Deutsch",
	"es": "Español",
	"fr": "Français",
	"id": "Bahasa Indonesia",
	"it": "Italiano",
	"ms": "Bahasa Melayu",
	"pl": "Język Polski",
	"ru": "русский язык",
	"sk": "Slovenčina",
	"sv": "Svenska",
	"ta": "தமிழ்",
	"tr": "Türkçe",
	"uk": "Українська",
	"vi": "tiếng Việt",
	"zh_CN": "汉语",
}

app.config.from_pyfile(os.environ["FLASK_CONFIG"])

if not app.config["ADMIN_CONTACT_URL"]:
	raise Exception("Missing config property: ADMIN_CONTACT_URL")

redis_client = redis.Redis.from_url(app.config["REDIS_URL"])

github = GitHub(app)
csrf = CSRFProtect(app)
mail = Mail(app)
pages = FlatPages(app)
babel = Babel()
init_markdown(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "users.login"


from .sass import init_app as sass
sass(app)


from . import models, template_filters


@login_manager.user_loader
def load_user(user_id):
	return models.User.query.filter_by(username=user_id).first()


from .blueprints import create_blueprints
create_blueprints(app)


@app.route("/uploads/<path:path>")
def send_upload(path):
	return send_from_directory(app.config["UPLOAD_DIR"], path)


@app.route("/<path:path>/")
def flatpage(path):
	page = pages.get_or_404(path)
	template = page.meta.get("template", "flatpage.html")
	return render_template(template, page=page)


@app.before_request
def check_for_ban():
	if current_user.is_authenticated:
		if current_user.ban and current_user.ban.has_expired:
			models.db.session.delete(current_user.ban)
			if current_user.rank == models.UserRank.BANNED:
				current_user.rank = models.UserRank.MEMBER
			models.db.session.commit()
		elif current_user.is_banned:
			if current_user.ban:
				flash(gettext("Banned:") + " " + current_user.ban.message, "danger")
			else:
				flash(gettext("You have been banned."), "danger")
			logout_user()
			return redirect(url_for("users.login"))
		elif current_user.rank == models.UserRank.NOT_JOINED:
			current_user.rank = models.UserRank.NEW_MEMBER
			models.db.session.commit()


from .utils import clear_notifications, is_safe_url, create_session


@app.before_request
def check_for_notifications():
	clear_notifications(request.path)


@app.errorhandler(404)
def page_not_found(e):
	return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
	return render_template("500.html"), 500


def get_locale():
	if not request:
		return None

	locales = app.config["LANGUAGES"].keys()

	if current_user.is_authenticated and current_user.locale in locales:
		return current_user.locale

	locale = request.cookies.get("locale")
	if locale not in locales:
		locale = request.accept_languages.best_match(locales)

	if locale and current_user.is_authenticated:
		with create_session() as new_session:
			new_session.query(models.User) \
				.filter(models.User.username == current_user.username) \
				.update({"locale": locale})
			new_session.commit()

	return locale


babel.init_app(app, locale_selector=get_locale)


@app.route("/set-locale/", methods=["POST"])
@csrf.exempt
def set_locale():
	locale = request.form.get("locale")
	if locale not in app.config["LANGUAGES"].keys():
		flash("Unknown locale {}".format(locale), "danger")
		locale = None

	next_url = request.form.get("r")
	if next_url and is_safe_url(next_url):
		resp = make_response(redirect(next_url))
	else:
		resp = make_response(redirect(url_for("homepage.home")))

	if locale:
		expire_date = datetime.datetime.now()
		expire_date = expire_date + datetime.timedelta(days=5*365)
		resp.set_cookie("locale", locale, expires=expire_date, secure=True, samesite="Lax")

		if current_user.is_authenticated:
			current_user.locale = locale
			models.db.session.commit()

	return resp


@app.route("/set-nonfree/", methods=["POST"])
def set_nonfree():
	resp = redirect(url_for("homepage.home"))
	if request.cookies.get("hide_nonfree") == "1":
		resp.set_cookie("hide_nonfree", "0", expires=0, secure=True, samesite="Lax")
	else:
		expire_date = datetime.datetime.now()
		expire_date = expire_date + datetime.timedelta(days=5*365)
		resp.set_cookie("hide_nonfree", "1", expires=expire_date, secure=True, samesite="Lax")

	return resp
