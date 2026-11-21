# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
import hashlib
import importlib.util
import io
import json
import os
import shutil
import zipfile
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup
from PIL import Image
from sqlalchemy import text

from app import app
from app.models import db, User, UserRank, AuditLogEntry, DashboardWidgetType
from app.blueprints.users import account
from app.utils.gravatar import get_gravatar_url, get_gravatar_proxy_url
from app.utils.phpbbparser import Profile
from app.tasks import forumtasks
from app.tasks.usertasks import set_profile_picture_from_url
from ..factories import client_request, create_user, create_package, create_review, create_dashboard, login_as, \
	get_user


@pytest.fixture(autouse=True)
def gravatar_cache():
	"""
	The cache is keyed by user id, which the next test reuses, so empty it
	"""
	path = os.path.join(app.config["THUMBNAIL_DIR"], "gravatar")
	shutil.rmtree(path, ignore_errors=True)
	yield
	shutil.rmtree(path, ignore_errors=True)


def make_image(fmt: str = "JPEG") -> bytes:
	out = io.BytesIO()
	Image.new("RGB", (80, 80), (200, 30, 30)).save(out, format=fmt)
	return out.getvalue()


def create_gravatar_user(username: str = "member", email: str = "Member@Example.com") -> User:
	user = create_user(username, email=email)
	user.use_gravatar = True
	db.session.commit()
	return user


def proxy_url(user: User) -> str:
	return get_gravatar_proxy_url(user)


def test_profile_links_to_proxy_without_exposing_hash(client):
	user = create_gravatar_user()

	url = user.get_profile_pic_url()
	assert url == proxy_url(user)
	assert url.startswith(f"/thumbnails/gravatar/{user.id}.png?v=")

	html = client_request(client, "GET", "/users/member/").data.decode("utf-8")
	assert url in html
	for email in ["Member@Example.com", "member@example.com"]:
		assert hashlib.sha256(email.encode()).hexdigest() not in html
		assert hashlib.md5(email.encode(), usedforsecurity=False).hexdigest() not in html
	assert "gravatar.com" not in html


def test_not_opted_in_uses_default(client):
	user = create_user("member", email="member@example.com")
	assert user.get_profile_pic_url() == "/static/default_avatar.png"


def test_opted_in_without_email_uses_default(client):
	user = create_user("member", email=None)
	user.use_gravatar = True
	db.session.commit()
	assert user.get_profile_pic_url() == "/static/default_avatar.png"


def test_url_changes_with_email(client):
	user = create_gravatar_user()
	before = proxy_url(user)

	user.email = "other@example.com"
	db.session.commit()
	assert proxy_url(user) != before

	# The case of the email doesn't matter, as for Gravatar
	user.email = "OTHER@example.com"
	db.session.commit()
	assert proxy_url(get_user("member")) == proxy_url(user)


def test_proxy_serves_and_caches(client, http_stub):
	user = create_gravatar_user()
	http_stub.add("GET", get_gravatar_url("member@example.com"), body=make_image("JPEG"),
			headers={"Content-Type": "image/jpeg"})

	rv = client_request(client, "GET", proxy_url(user))
	assert rv.status_code == 200
	assert rv.mimetype == "image/png"
	assert "max-age=86400" in rv.headers["Cache-Control"]
	with Image.open(io.BytesIO(rv.data)) as image:
		assert image.format == "PNG"
		assert image.size == (80, 80)

	rv = client_request(client, "GET", proxy_url(user))
	assert rv.status_code == 200
	assert len(http_stub.calls) == 1

	# The request uses the SHA-256 of the lowercased email, and returns a 404 when there's no image
	assert http_stub.calls[0][1] == \
		f"https://gravatar.com/avatar/{hashlib.sha256(b'member@example.com').hexdigest()}?s=256&d=404&r=g"


def test_proxy_falls_back_without_gravatar(client, http_stub):
	user = create_gravatar_user()
	http_stub.add("GET", get_gravatar_url("member@example.com"), status=404)

	for _ in range(2):
		rv = client_request(client, "GET", proxy_url(user))
		assert rv.status_code == 302
		assert rv.headers["Location"] == "/static/default_avatar.png"

	# Not having a Gravatar is cached too
	assert len(http_stub.calls) == 1


def test_proxy_falls_back_to_forum_picture(client, http_stub):
	user = create_gravatar_user()
	user.profile_pic = "https://cdn.example.com/uploads/forum.png"
	db.session.commit()
	http_stub.add("GET", get_gravatar_url("member@example.com"), status=404)

	rv = client_request(client, "GET", proxy_url(user))
	assert rv.status_code == 302
	assert rv.headers["Location"] == "https://cdn.example.com/uploads/forum.png"


def test_proxy_errors_arent_cached(client, http_stub):
	user = create_gravatar_user()
	http_stub.add("GET", get_gravatar_url("member@example.com"), status=500)

	for _ in range(2):
		rv = client_request(client, "GET", proxy_url(user))
		assert rv.status_code == 302
		assert rv.headers["Location"] == "/static/default_avatar.png"
		assert "max-age=300" in rv.headers["Cache-Control"]

	assert len(http_stub.calls) == 2


def test_proxy_rejects_invalid_image(client, http_stub):
	user = create_gravatar_user()
	http_stub.add("GET", get_gravatar_url("member@example.com"), body="<svg>not an image</svg>",
			headers={"Content-Type": "image/svg+xml"})

	rv = client_request(client, "GET", proxy_url(user))
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/static/default_avatar.png"


def test_proxy_doesnt_fetch_for_users_who_havent_opted_in(client, http_stub):
	user = create_user("member", email="member@example.com")

	# http_stub fails the test on any request
	rv = client_request(client, "GET", f"/thumbnails/gravatar/{user.id}.png")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/static/default_avatar.png"


def test_proxy_unknown_user(client):
	rv = client_request(client, "GET", "/thumbnails/gravatar/999999.png")
	assert rv.status_code == 404


def test_proxy_uses_new_email(client, http_stub):
	user = create_gravatar_user()
	http_stub.add("GET", get_gravatar_url("member@example.com"), body=make_image("PNG"))
	http_stub.add("GET", get_gravatar_url("other@example.com"), status=404)

	assert client_request(client, "GET", proxy_url(user)).status_code == 200

	user.email = "other@example.com"
	db.session.commit()

	rv = client_request(client, "GET", proxy_url(user))
	assert rv.status_code == 302
	assert [call[1] for call in http_stub.calls] == \
		[get_gravatar_url("member@example.com"), get_gravatar_url("other@example.com")]


def test_user_can_turn_on_and_off(client):
	user = create_user("member", email="member@example.com")
	login_as(client, user)

	html = client_request(client, "GET", "/users/member/settings/profile/").data.decode("utf-8")
	assert "Use Gravatar" in html
	assert 'id="gravatar-help"' in html

	rv = client_request(client, "POST", "/users/member/gravatar/", data={"enable": "1"})
	assert rv.status_code == 302
	assert get_user("member").use_gravatar

	html = client_request(client, "GET", "/users/member/settings/profile/").data.decode("utf-8")
	assert "Stop using Gravatar" in html

	rv = client_request(client, "POST", "/users/member/gravatar/", data={"enable": "0"})
	assert rv.status_code == 302
	assert not get_user("member").use_gravatar


def test_needs_email(client):
	login_as(client, create_user("member", email=None))

	html = client_request(client, "GET", "/users/member/settings/profile/").data.decode("utf-8")
	assert "Add an email address to use Gravatar." in html

	rv = client_request(client, "POST", "/users/member/gravatar/", data={"enable": "1"}, follow_redirects=True)
	assert b"You need an email address to use Gravatar" in rv.data
	assert not get_user("member").use_gravatar


@pytest.mark.parametrize("rank", [UserRank.MEMBER, UserRank.MODERATOR, UserRank.ADMIN])
def test_others_cant_turn_on(client, rank):
	create_user("member", email="member@example.com")
	login_as(client, create_user("other", rank))

	rv = client_request(client, "POST", "/users/member/gravatar/", data={"enable": "1"})
	assert rv.status_code == 403
	assert not get_user("member").use_gravatar


def test_moderators_can_turn_off(client):
	create_gravatar_user()
	login_as(client, create_user("mod", UserRank.MODERATOR))

	html = client_request(client, "GET", "/users/member/settings/profile/").data.decode("utf-8")
	assert "Stop using Gravatar" in html
	assert 'id="gravatar-help"' not in html

	rv = client_request(client, "POST", "/users/member/gravatar/", data={"enable": "0"})
	assert rv.status_code == 302
	assert not get_user("member").use_gravatar
	assert AuditLogEntry.query.filter_by(title="Turned off Gravatar for member").count() == 1


def test_members_cant_turn_off_for_others(client):
	create_gravatar_user()
	login_as(client, create_user("other"))

	rv = client_request(client, "POST", "/users/member/gravatar/", data={"enable": "0"})
	assert rv.status_code == 403
	assert get_user("member").use_gravatar


def test_homepage_reviews_show_gravatar(client):
	"""The reviews widget only loads some user columns"""
	reviewer = create_gravatar_user("reviewer", "reviewer@example.com")
	create_review(reviewer, create_package("SomeMod", create_user("author")), comment="Great")
	create_dashboard([(DashboardWidgetType.REVIEWS, "Reviews", None, 5)])

	rv = client_request(client, "GET", "/")
	assert rv.status_code == 200
	assert f"/thumbnails/gravatar/{reviewer.id}.png".encode() in rv.data


def register(client, **extra):
	return client_request(client, "POST", "/user/register/", data=dict(
			username="newuser", email="newuser@example.com", password="VYjNnjdDPhCVUZx", question="19", **extra))


def test_register_form_has_gravatar_ticked(client):
	soup = BeautifulSoup(client_request(client, "GET", "/user/register/").data.decode("utf-8"), "html.parser")
	checkbox = soup.find("input", attrs={"name": "use_gravatar"})
	assert checkbox is not None
	assert checkbox.has_attr("checked")


@pytest.mark.parametrize("ticked", [True, False])
def test_register_sets_gravatar(client, monkeypatch, ticked):
	monkeypatch.setattr(account, "send_verify_email", MagicMock())

	rv = register(client, **({"use_gravatar": "y"} if ticked else {}))
	assert rv.status_code == 302
	assert get_user("newuser").use_gravatar == ticked


def run_migration_upgrade(monkeypatch) -> None:
	"""
	Runs the migration's data update against the test database. The column already exists, from the models.
	"""
	path = os.path.join(os.path.dirname(app.root_path), "migrations", "versions", "5e2a9c7d3b18_.py")
	spec = importlib.util.spec_from_file_location("gravatar_migration", path)
	assert spec is not None and spec.loader is not None
	migration = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(migration)

	statements: list[str] = []
	fake_op = MagicMock()
	fake_op.execute.side_effect = statements.append
	monkeypatch.setattr(migration, "op", fake_op)
	migration.upgrade()

	assert len(statements) == 1
	db.session.execute(text(statements[0]))
	db.session.commit()


def test_migration_opts_in_users_from_before_removal(client, monkeypatch):
	def make(username: str, created_at: datetime.datetime | None, has_email: bool = True,
			profile_pic: str | None = None):
		user = create_user(username, email=f"{username}@example.com" if has_email else None)
		# Set after inserting, as created_at has a Python default
		user.created_at = created_at
		user.profile_pic = profile_pic
		db.session.commit()

	make("old", datetime.datetime(2026, 10, 1))
	make("no_date", None)
	make("day_before", datetime.datetime(2026, 10, 25, 23, 59))
	make("on_the_day", datetime.datetime(2026, 10, 26, 0, 0))
	make("new", datetime.datetime(2026, 11, 1))
	make("old_with_picture", datetime.datetime(2026, 10, 1), profile_pic="/uploads/abc.png")
	make("old_with_empty_picture", datetime.datetime(2026, 10, 1), profile_pic="")
	make("old_without_email", datetime.datetime(2026, 10, 1), has_email=False)

	run_migration_upgrade(monkeypatch)

	db.session.expire_all()
	opted_in = {x.username for x in User.query.filter_by(use_gravatar=True).all()}
	assert opted_in == {"old", "no_date", "day_before", "old_with_empty_picture"}


def test_profile_pic_beats_gravatar(client):
	user = create_gravatar_user()
	# Normally only one is set, but a profile picture wins if both are
	user.profile_pic = "/uploads/forum.png"
	db.session.commit()
	assert user.get_profile_pic_url() == "/uploads/forum.png"


def test_set_profile_pic_turns_off_gravatar(client):
	user = create_gravatar_user()
	user.set_profile_pic("/uploads/forum.png")
	assert user.profile_pic == "/uploads/forum.png" and not user.use_gravatar

	user.set_use_gravatar(True)
	assert user.profile_pic is None and user.use_gravatar

	# Removing a picture doesn't change Gravatar
	user.set_profile_pic(None)
	assert user.use_gravatar


def test_turning_on_gravatar_removes_profile_pic(client):
	user = create_user("member", email="member@example.com")
	user.profile_pic = "/uploads/forum.png"
	db.session.commit()
	login_as(client, user)

	html = client_request(client, "GET", "/users/member/settings/profile/").data.decode("utf-8")
	assert "Using Gravatar will remove your current profile picture." in html

	rv = client_request(client, "POST", "/users/member/gravatar/", data={"enable": "1"})
	assert rv.status_code == 302

	user = get_user("member")
	assert user.use_gravatar
	assert user.profile_pic is None
	assert user.get_profile_pic_url() == proxy_url(user)


def test_turning_off_gravatar_keeps_no_picture(client):
	create_gravatar_user()
	login_as(client, get_user("member"))

	client_request(client, "POST", "/users/member/gravatar/", data={"enable": "0"})

	user = get_user("member")
	assert not user.use_gravatar
	assert user.get_profile_pic_url() == "/static/default_avatar.png"


@pytest.fixture
def forum_profile(monkeypatch) -> MagicMock:
	"""
	Stubs the forum profile, with an avatar, and records profile pictures queued for download
	"""
	profile = Profile("ForumName")
	profile.avatar = "./download/file.php?avatar=123.png"
	monkeypatch.setattr(forumtasks, "get_profile", lambda url, username: profile)

	queued = MagicMock()
	monkeypatch.setattr(forumtasks, "set_profile_picture_from_url", queued)
	return queued.delay


FORUM_AVATAR = "https://forum.luanti.org/download/file.php?avatar=123.png"


def create_forum_user(gravatar: bool) -> User:
	user = create_user("member", email="member@example.com")
	user.forums_username = "ForumName"
	user.use_gravatar = gravatar
	db.session.commit()
	return user


def test_forum_check_doesnt_replace_gravatar(client, forum_profile):
	create_forum_user(gravatar=True)

	forumtasks.check_forum_account("ForumName")

	forum_profile.assert_not_called()


def test_forum_import_replaces_gravatar_when_asked(client, forum_profile):
	create_forum_user(gravatar=True)

	forumtasks.check_forum_account("ForumName", force_replace_pic=True)

	forum_profile.assert_called_once_with("member", FORUM_AVATAR, True)


def test_forum_check_sets_picture_without_gravatar(client, forum_profile):
	create_forum_user(gravatar=False)

	forumtasks.check_forum_account("ForumName")

	forum_profile.assert_called_once_with("member", FORUM_AVATAR, False)


def test_downloaded_picture_turns_off_gravatar(client, http_stub):
	create_forum_user(gravatar=True)
	http_stub.add("GET", FORUM_AVATAR, body=make_image("PNG"), headers={"Content-Type": "image/png"})

	set_profile_picture_from_url.apply(args=["member", FORUM_AVATAR, True]).get()

	user = get_user("member")
	assert user.profile_pic is not None and user.profile_pic.startswith("/uploads/")
	assert not user.use_gravatar
	assert user.get_profile_pic_url() == user.profile_pic


def test_automatic_download_skips_gravatar_users(client, http_stub):
	"""The user may turn Gravatar on after the download was queued"""
	create_forum_user(gravatar=True)

	# http_stub fails the test on any request
	set_profile_picture_from_url.apply(args=["member", FORUM_AVATAR]).get()

	user = get_user("member")
	assert user.use_gravatar
	assert user.profile_pic is None


def test_api_shows_gravatar_proxy(client):
	user = create_gravatar_user()

	rv = client_request(client, "GET", "/api/users/member/")
	assert rv.status_code == 200
	assert rv.json is not None
	assert rv.json["profile_pic_url"] == app.config["BASE_URL"] + proxy_url(user)
	assert "gravatar.com" not in rv.data.decode("utf-8")


def test_api_profile_pic_without_gravatar(client):
	create_user("nopic", email="nopic@example.com")
	forum = create_user("forum", email="forum@example.com")
	forum.profile_pic = "https://cdn.example.com/uploads/forum.png"
	db.session.commit()

	def get_profile_pic_url(username: str):
		data = client_request(client, "GET", f"/api/users/{username}/").json
		assert data is not None
		return data["profile_pic_url"]

	assert get_profile_pic_url("nopic") is None
	assert get_profile_pic_url("forum") == "https://cdn.example.com/uploads/forum.png"


def test_database_dump_doesnt_include_gravatar(client, monkeypatch, tmp_path):
	"""An importer would otherwise store this instance's proxy URL as the user's profile picture"""
	from app.tasks.dumptask import create_database_dump
	from app.uploads import local

	monkeypatch.setattr(local, "upload_dir", str(tmp_path))
	user = create_gravatar_user()
	create_package("SomeMod", user)

	create_database_dump()

	date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
	with zipfile.ZipFile(tmp_path / f"backup-{date}.zip") as zipf:
		data = json.loads(zipf.read("backup/member/index.json"))
	assert data["profile_pic_url"] is None
