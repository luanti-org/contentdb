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

from flask import *
from flask_gravatar import Gravatar
from flask_mail import Mail
from flask_github import GitHub
from flask_wtf.csrf import CSRFProtect
from flask_flatpages import FlatPages
from flask_babel import Babel, gettext
from flask_login import logout_user, current_user, LoginManager
import os, redis
from app.markdown import init_markdown, MARKDOWN_EXTENSIONS, MARKDOWN_EXTENSION_CONFIG

app = Flask(__name__, static_folder="public/static")
app.config["FLATPAGES_ROOT"] = "flatpages"
app.config["FLATPAGES_EXTENSION"] = ".md"
app.config["FLATPAGES_MARKDOWN_EXTENSIONS"] = MARKDOWN_EXTENSIONS
app.config["FLATPAGES_EXTENSION_CONFIG"] = MARKDOWN_EXTENSION_CONFIG
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "../translations"
app.config["LANGUAGES"] = {
	"en": "English",
	"de": "Deutsch",
	"fr": "Français",
	"id": "Bahasa Indonesia",
	"it": "Italiano",
	"ms": "Bahasa Melayu",
	"pl": "Język Polski",
	"ru": "русский язык",
	"sk": "Slovenčina",
	"sv": "Svenska",
	"uk": "Українська",
	"vi": "tiếng Việt",
	"zh_Hans": "汉语",
}

app.config.from_pyfile(os.environ["FLASK_CONFIG"])

r = redis.Redis.from_url(app.config["REDIS_URL"])

github = GitHub(app)
csrf = CSRFProtect(app)
mail = Mail(app)
pages = FlatPages(app)
babel = Babel()
gravatar = Gravatar(app,
		size=64,
		rating="g",
		default="retro",
		force_default=False,
		force_lower=False,
		use_ssl=True,
		base_url=None)
init_markdown(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "users.login"


from .sass import init_app as sass
sass(app)


if not app.debug and app.config["MAIL_UTILS_ERROR_SEND_TO"]:
	from .maillogger import build_handler
	app.logger.addHandler(build_handler(app))


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
		elif current_user.ban or current_user.rank == models.UserRank.BANNED:
			if current_user.ban:
				flash(gettext("Banned:") + " " + current_user.ban.message, "danger")
			else:
				flash(gettext("You have been banned."), "danger")
			logout_user()
			return redirect(url_for("users.login"))
		elif current_user.rank == models.UserRank.NOT_JOINED:
			current_user.rank = models.UserRank.NEW_MEMBER
			models.db.session.commit()


from .utils import clearNotifications, is_safe_url


@app.before_request
def check_for_notifications():
	if current_user.is_authenticated:
		clearNotifications(request.path)


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
		with models.db.create_session({})() as new_session:
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
		resp.set_cookie("locale", locale, expires=expire_date)

		if current_user.is_authenticated:
			current_user.locale = locale
			models.db.session.commit()

	return resp
