# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
import re
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from bs4 import BeautifulSoup

from app import app, redis_client
from app.models import db, EmailSubscription, AuditLogEntry, UserRank, UserEmailVerification
from app.rediscache import EMAIL_BOUNCES_LAST_IMPORT_KEY, get_email_bounces_last_import, \
	set_email_bounces_last_import
from app.tasks.emails import import_email_bounces, send_user_email, send_verify_email, send_single_email, \
	send_notification_digest
from app.utils.scaleway_tem import ScalewayTEMError, PAGE_SIZE
from ..factories import client_request, create_user, login_as, get_user, DEFAULT_PASSWORD
from .test_github_oauth import stub_github, start as github_start, callback as github_callback


API = "https://api.scaleway.com/transactional-email/v1alpha1/regions/fr-par"
EMAILS_URL = f"{API}/emails"
BLOCKLISTS_URL = f"{API}/blocklists"


@pytest.fixture
def tem(monkeypatch):
	"""
	Configures Scaleway TEM, and forgets the last import, which is kept in Redis between tests
	"""
	monkeypatch.setitem(app.config, "SCALEWAY_TEM_SECRET_KEY", "secret")
	monkeypatch.setitem(app.config, "SCALEWAY_TEM_PROJECT_ID", "project")
	monkeypatch.setitem(app.config, "SCALEWAY_TEM_DOMAIN_ID", None)
	monkeypatch.setitem(app.config, "SCALEWAY_TEM_REGION", None)
	redis_client.delete(EMAIL_BOUNCES_LAST_IMPORT_KEY)
	yield
	redis_client.delete(EMAIL_BOUNCES_LAST_IMPORT_KEY)


def api_time(value: datetime.datetime) -> str:
	return value.isoformat() + "Z"


def failed_email(rcpt: str, flags: list[str], created_at: datetime.datetime | None = None, code: int | None = 550):
	created_at = created_at or datetime.datetime.utcnow() - datetime.timedelta(hours=1)
	return {
		"id": "id-" + rcpt,
		"message_id": "<msg@example.com>",
		"mail_rcpt": rcpt,
		"status": "failed",
		"flags": flags,
		"try_count": 3,
		"last_tries": [
			{"rank": 1, "code": 421, "message": "try again"},
			{"rank": 3, "code": code, "message": "no"},
		] if code else [],
		"created_at": api_time(created_at),
	}


def get_sub(email: str) -> EmailSubscription | None:
	db.session.expire_all()
	return EmailSubscription.query_by_email(email).first()


def make_bounced(email: str, reason: str = "mailbox_not_found (550)"):
	sub = EmailSubscription(email)
	sub.bounced_at = datetime.datetime.utcnow()
	sub.bounce_reason = reason
	db.session.add(sub)
	db.session.commit()
	return sub


def test_import_records_bounces(client, http_stub, tem):
	create_user("dead", email="dead@example.com")
	http_stub.add("GET", EMAILS_URL, json={"total_count": 4, "emails": [
		failed_email("dead@example.com", ["soft_bounce", "mailbox_not_found"]),
		failed_email("soft@example.com", ["soft_bounce", "mailbox_full"]),
		failed_email("spam@example.com", ["spam"], code=None),
		failed_email("nobody@example.com", ["hard_bounce"]),
	]})

	before = datetime.datetime.utcnow()
	import_email_bounces.apply(args=[60]).get()

	dead = get_sub("dead@example.com")
	assert dead is not None and dead.bounced_at is not None
	assert dead.bounce_reason == "mailbox_not_found (550)"
	assert not dead.can_send

	spam = get_sub("spam@example.com")
	assert spam is not None and spam.bounce_reason == "spam"

	nobody = get_sub("nobody@example.com")
	assert nobody is not None and nobody.bounce_reason == "hard_bounce (550)"

	soft = get_sub("soft@example.com")
	assert soft is None or soft.bounced_at is None

	# An audit entry for the user, without the address
	entry = AuditLogEntry.query.filter(AuditLogEntry.title.like("Email to dead%")).one()
	assert entry.title == "Email to dead can't be delivered: mailbox_not_found (550)"
	assert entry.url == "/users/dead/"

	# The request
	assert len(http_stub.calls) == 1
	method, url, kwargs = http_stub.calls[0]
	params = kwargs["params"]
	assert kwargs["headers"]["X-Auth-Token"] == "secret"
	assert params["project_id"] == "project"
	assert params["statuses"] == ["failed"]
	assert params["page"] == 1
	since = datetime.datetime.fromisoformat(params["since"].removesuffix("Z"))
	expected = before - datetime.timedelta(days=60)
	assert abs((since - expected).total_seconds()) < 60


def test_import_reads_all_pages(client, http_stub, tem):
	first = [failed_email(f"user{i}@example.com", ["soft_bounce"]) for i in range(PAGE_SIZE)]
	http_stub.add("GET", EMAILS_URL, json={"emails": first})
	http_stub.add("GET", EMAILS_URL, json={"emails": [failed_email("last@example.com", ["mailbox_not_found"])]})

	import_email_bounces.apply(args=[60]).get()

	assert [call[2]["params"]["page"] for call in http_stub.calls] == [1, 2]
	last = get_sub("last@example.com")
	assert last is not None and last.bounced_at is not None


def test_import_does_nothing_when_not_configured(client, http_stub):
	# http_stub fails the test on any request
	import_email_bounces.apply(args=[60]).get()
	assert http_stub.calls == []


def test_import_continues_from_last_import(client, http_stub, tem):
	http_stub.add("GET", EMAILS_URL, json={"emails": []})

	last = datetime.datetime(2026, 10, 27, 12, 0, 0)
	set_email_bounces_last_import(last)

	before = datetime.datetime.utcnow()
	import_email_bounces.apply().get()

	# Looks back past the last import, to catch emails that were still being retried
	assert http_stub.calls[0][2]["params"]["since"] == "2026-10-23T12:00:00Z"

	recorded = get_email_bounces_last_import()
	assert recorded is not None and recorded >= before


def test_first_import_looks_back_four_days(client, http_stub, tem):
	http_stub.add("GET", EMAILS_URL, json={"emails": []})

	before = datetime.datetime.utcnow()
	import_email_bounces.apply().get()

	since = datetime.datetime.fromisoformat(http_stub.calls[0][2]["params"]["since"].removesuffix("Z"))
	assert abs((since - (before - datetime.timedelta(days=4))).total_seconds()) < 60


def test_failed_import_keeps_last_import(client, http_stub, tem):
	http_stub.add("GET", EMAILS_URL, status=500, body="error")

	last = datetime.datetime(2026, 10, 27, 12, 0, 0)
	set_email_bounces_last_import(last)

	with pytest.raises(ScalewayTEMError):
		import_email_bounces.apply().get()

	assert get_email_bounces_last_import() == last


def test_import_reads_blocklists(client, http_stub, tem, monkeypatch):
	monkeypatch.setitem(app.config, "SCALEWAY_TEM_DOMAIN_ID", "domain")
	now = datetime.datetime.utcnow()
	http_stub.add("GET", EMAILS_URL, json={"emails": []})
	http_stub.add("GET", BLOCKLISTS_URL, json={"blocklists": [
		{"email": "gone@example.com", "type": "mailbox_not_found", "custom": False,
			"created_at": api_time(now - datetime.timedelta(days=3)), "ends_at": None},
		{"email": "full@example.com", "type": "mailbox_full", "custom": False,
			"created_at": api_time(now), "ends_at": api_time(now + datetime.timedelta(days=1))},
		{"email": "expired@example.com", "type": "mailbox_not_found", "custom": False,
			"created_at": api_time(now - datetime.timedelta(days=10)),
			"ends_at": api_time(now - datetime.timedelta(days=1))},
		{"email": "manual@example.com", "type": "mailbox_not_found", "custom": True,
			"created_at": api_time(now), "ends_at": None},
	]})

	import_email_bounces.apply(args=[60]).get()

	assert http_stub.calls[1][2]["params"]["domain_id"] == "domain"

	gone = get_sub("gone@example.com")
	assert gone is not None and gone.bounce_reason == "blocklist: mailbox_not_found"
	for email in ["full@example.com", "expired@example.com", "manual@example.com"]:
		sub = get_sub(email)
		assert sub is None or sub.bounced_at is None, email


def test_failures_from_before_confirmation_are_ignored(client, http_stub, tem):
	now = datetime.datetime.utcnow()
	for email in ["old@example.com", "new@example.com"]:
		sub = EmailSubscription(email)
		sub.bounce_cleared_at = now - datetime.timedelta(hours=2)
		db.session.add(sub)
	db.session.commit()

	http_stub.add("GET", EMAILS_URL, json={"emails": [
		failed_email("old@example.com", ["mailbox_not_found"], created_at=now - datetime.timedelta(hours=3)),
		failed_email("new@example.com", ["mailbox_not_found"], created_at=now - datetime.timedelta(hours=1)),
	]})

	import_email_bounces.apply(args=[60]).get()

	old = get_sub("old@example.com")
	assert old is not None and old.bounced_at is None
	new = get_sub("new@example.com")
	assert new is not None and new.bounced_at is not None


def test_bounced_address_is_only_sent_verification_emails(client, eager_tasks, mailpit):
	make_bounced("dead@example.com")
	user = SimpleNamespace(email="dead@example.com", display_name="Dead", username="dead")
	notification = SimpleNamespace(user=user, title="Hello", url="/", causer=user)

	send_user_email.delay("dead@example.com", "en", "Test subject", "Test body text")
	send_single_email(notification, "en")
	send_notification_digest([notification, notification], "en")  # type: ignore[list-item]
	send_verify_email.delay("dead@example.com", "token", "en")

	mailpit.wait_for("dead@example.com")
	# Sent last, so the others were handled by the time it arrives
	send_user_email.delay("other@example.com", "en", "Other subject", "Other body text")
	mailpit.wait_for("other@example.com")

	messages = mailpit.messages_to("dead@example.com")
	assert [x["Subject"] for x in messages] == ["Confirm email address"]


def test_banner_is_shown_to_bounced_user(client):
	user = create_user("dead", email="dead@example.com")
	login_as(client, user)

	rv = client_request(client, "GET", "/")
	assert b"email-bounce-alert" not in rv.data

	make_bounced("dead@example.com")

	rv = client_request(client, "GET", "/")
	assert rv.status_code == 200
	assert b"email-bounce-alert" in rv.data
	assert b"/users/dead/settings/email/" in rv.data

	# The settings page explains instead
	rv = client_request(client, "GET", "/users/dead/settings/email/")
	assert rv.status_code == 200
	assert b"email-bounce-alert" not in rv.data
	assert b"email-bounce-status" in rv.data
	assert b"mailbox_not_found (550)" in rv.data


def test_banner_isnt_shown_for_other_addresses(client):
	make_bounced("someone-else@example.com")
	login_as(client, create_user("member", email="member@example.com"))

	rv = client_request(client, "GET", "/")
	assert b"email-bounce-alert" not in rv.data


def test_reverify_clears_bounce(client, eager_tasks, mailpit):
	user = create_user("dead", email="dead@example.com")
	make_bounced("dead@example.com")
	login_as(client, user)

	rv = client_request(client, "POST", "/users/dead/settings/email/verify/")
	assert rv.status_code == 302
	assert rv.headers["Location"].endswith("/email_sent/")

	message = mailpit.wait_for("dead@example.com")
	match = re.search(r"token=([A-Za-z0-9]+)", mailpit.get_text(message))
	assert match

	before = datetime.datetime.utcnow()
	rv = client_request(client, "GET", f"/user/verify/?token={match.group(1)}", follow_redirects=True)
	assert rv.status_code == 200
	assert b"emails will be sent to it again" in rv.data

	sub = get_sub("dead@example.com")
	assert sub is not None and sub.bounced_at is None and sub.bounce_reason is None
	assert sub.bounce_cleared_at is not None and sub.bounce_cleared_at >= before

	rv = client_request(client, "GET", "/")
	assert b"email-bounce-alert" not in rv.data


def test_staff_verifying_doesnt_clear_bounce(client):
	user = create_user("dead", email="dead@example.com")
	make_bounced("dead@example.com")

	ver = UserEmailVerification()
	ver.user = user
	ver.email = "dead@example.com"
	ver.token_hash = "abc"
	db.session.add(ver)
	db.session.commit()

	login_as(client, create_user("mod", UserRank.MODERATOR))

	rv = client_request(client, "GET", "/users/dead/modtools/")
	assert rv.status_code == 200
	assert b"email-bounce-status" in rv.data

	rv = client_request(client, "POST", f"/users/dead/modtools/verify-email/{ver.id}/")
	assert rv.status_code == 302

	sub = get_sub("dead@example.com")
	assert sub is not None and sub.bounced_at is not None


def password_login(client, username: str = "dead", next_url: str | None = None):
	url = "/user/login/" + (f"?next={quote(next_url)}" if next_url else "")
	return client_request(client, "POST", url, data={"username": username, "password": DEFAULT_PASSWORD})


def test_login_asks_bounced_user_to_confirm_email(client):
	create_user("dead", email="dead@example.com")
	make_bounced("dead@example.com")

	rv = password_login(client)
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/email-bounced/"

	rv = client_request(client, "GET", "/user/email-bounced/")
	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "dead@example.com" in html
	assert 'action="/users/dead/settings/email/verify/"' in html
	assert 'name="next"' not in html
	assert 'href="/users/dead/settings/email/"' in html
	assert "email-bounce-alert" not in html


def test_login_doesnt_ask_when_email_works(client):
	create_user("member", email="member@example.com")
	make_bounced("someone-else@example.com")

	rv = password_login(client, "member", next_url="/packages/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/"


def test_bounce_prompt_comes_before_next_link(client):
	create_user("dead", email="dead@example.com")
	make_bounced("dead@example.com")

	rv = password_login(client, next_url="/packages/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/email-bounced/?next=/packages/"

	html = client_request(client, "GET", "/user/email-bounced/?next=/packages/").data.decode("utf-8")
	assert '<input type="hidden" name="next" value="/packages/">' in html
	assert 'href="/packages/"' in html


def test_unsafe_next_link_is_dropped(client):
	create_user("dead", email="dead@example.com")
	make_bounced("dead@example.com")

	# The login page already refuses it
	rv = password_login(client, next_url="https://example.com/")
	assert rv.status_code == 400

	# The prompt drops it if it's given one directly
	login_as(client, get_user("dead"))
	rv = client_request(client, "GET", "/user/email-bounced/?next=https://example.com/")
	soup = BeautifulSoup(rv.data.decode("utf-8"), "html.parser")
	main = soup.find("main")
	assert main is not None
	assert main.find("input", attrs={"name": "next"}) is None
	assert main.find("a", href="https://example.com/") is None
	assert main.find("a", string=re.compile("Not now"), href="/") is not None


def test_confirming_from_prompt_goes_on_to_next_link(client, eager_tasks, mailpit):
	user = create_user("dead", email="dead@example.com")
	make_bounced("dead@example.com")
	login_as(client, user)

	rv = client_request(client, "POST", "/users/dead/settings/email/verify/", data={"next": "/packages/"})
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/"
	mailpit.wait_for("dead@example.com")

	rv = client_request(client, "GET", "/packages/")
	assert b"sent a verification email to dead@example.com" in rv.data


def test_confirming_ignores_unsafe_next_link(client, eager_tasks, mailpit):
	user = create_user("dead", email="dead@example.com")
	make_bounced("dead@example.com")
	login_as(client, user)

	rv = client_request(client, "POST", "/users/dead/settings/email/verify/", data={"next": "https://example.com/"})
	assert rv.status_code == 302
	assert rv.headers["Location"].endswith("/email_sent/")


def test_setting_a_password_comes_before_next_link(client, http_stub):
	create_user("member", email="member@example.com", password=None, github_user_id=1234)
	stub_github(http_stub, login="member")

	rv = github_callback(client, github_start(client, "/packages/"), "/packages/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/set-password/?next=/packages/"

	rv = client_request(client, "POST", "/user/set-password/?next=/packages/",
			data={"password": DEFAULT_PASSWORD, "password2": DEFAULT_PASSWORD})
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/packages/"


def test_setting_a_password_then_asks_about_bounce(client, http_stub):
	create_user("dead", email="dead@example.com", password=None, github_user_id=1234)
	make_bounced("dead@example.com")
	stub_github(http_stub, login="dead")

	rv = github_callback(client, github_start(client, "/packages/"), "/packages/")
	assert rv.headers["Location"] == "/user/set-password/?next=/packages/"

	rv = client_request(client, "POST", "/user/set-password/?next=/packages/",
			data={"password": DEFAULT_PASSWORD, "password2": DEFAULT_PASSWORD})
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/email-bounced/?next=/packages/"


def test_setting_a_password_without_next_link(client, http_stub):
	create_user("dead", email="dead@example.com", password=None, github_user_id=1234)
	make_bounced("dead@example.com")
	stub_github(http_stub, login="dead")

	rv = github_callback(client, github_start(client))
	assert rv.headers["Location"] == "/user/set-password/"

	rv = client_request(client, "POST", "/user/set-password/",
			data={"password": DEFAULT_PASSWORD, "password2": DEFAULT_PASSWORD})
	assert rv.headers["Location"] == "/user/email-bounced/"


def test_github_login_asks_bounced_user(client, http_stub):
	create_user("dead", email="dead@example.com", github_user_id=1234)
	make_bounced("dead@example.com")
	stub_github(http_stub, login="dead")

	rv = github_callback(client, github_start(client, "/packages/"), "/packages/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/user/email-bounced/?next=/packages/"


def test_email_bounced_page_redirects_when_email_works(client):
	login_as(client, create_user("member", email="member@example.com"))

	rv = client_request(client, "GET", "/user/email-bounced/")
	assert rv.status_code == 302
	assert rv.headers["Location"] == "/"

	rv = client_request(client, "GET", "/user/email-bounced/?next=/packages/")
	assert rv.headers["Location"] == "/packages/"


def test_email_bounced_page_needs_login(client):
	rv = client_request(client, "GET", "/user/email-bounced/")
	assert rv.status_code == 302
	assert "/user/login/" in rv.headers["Location"]
