# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Reports: creating them, and staff viewing, resolving and editing them.
"""

import io

import pytest

from app.models import db, User, UserRank, Report, ReportAttachment, ReportCategory, AuditLogEntry, Thread, \
	ThreadReply
from ..factories import create_user, create_thread, create_report, login_as, client_request
from ..packages.test_uploads import make_image


def report_form(**extra):
	return {
		"category": "SPAM",
		"url": "https://example.com/spam",
		"title": "This package is spam",
		"message": "Please remove it",
		**extra,
	}


def test_anonymous_users_cant_report(client):
	rv = client_request(client, "GET", "/report/")
	assert rv.status_code == 200
	assert "we no longer accept reports from anonymous users" in rv.data.decode("utf-8")

	rv = client_request(client, "POST", "/report/", data=report_form())
	assert rv.status_code == 200
	assert Report.query.count() == 0


def test_report(client):
	reporter = create_user("reporter")
	moderator = create_user("moderator", UserRank.MODERATOR)
	create_user("editor", UserRank.EDITOR)
	login_as(client, reporter)

	rv = client_request(client, "POST", "/report/", data=report_form())

	report = Report.query.one()
	assert rv.status_code == 302
	assert rv.headers["Location"] == f"/report/received/?rid={report.id}"
	assert report.user == reporter
	assert report.category == ReportCategory.SPAM
	assert report.title == "This package is spam"
	assert not report.is_resolved
	assert report.attachments.count() == 0

	# A private thread, so the reporter can talk to moderators
	thread = report.thread
	assert thread.private
	assert thread.author == reporter
	assert thread.title == "Report: This package is spam"
	watchers = {x.username for x in thread.watchers}
	assert moderator.username in watchers
	assert watchers == {x.username for x in User.query.filter(User.rank >= UserRank.MODERATOR).all()}
	assert "Please remove it" in thread.first_reply.comment
	assert not thread.check_perm(create_user("stranger"), "SEE_THREAD")

	assert AuditLogEntry.query.filter_by(title="New report: This package is spam").one().causer == reporter


def test_report_url_cant_be_report_page(client):
	login_as(client, create_user("reporter"))

	rv = client_request(client, "GET", "/report/?url=/report/")
	assert rv.status_code == 404


def test_report_with_attachment(client):
	login_as(client, create_user("reporter"))

	rv = client_request(client, "POST", "/report/", content_type="multipart/form-data",
			data=report_form(file_upload=(io.BytesIO(make_image()), "evidence.png")))

	assert rv.status_code == 302
	[attachment] = ReportAttachment.query.all()
	assert attachment.report == Report.query.one()
	assert attachment.upload_path.startswith("/uploads/")
	assert "evidence" not in attachment.upload_path


@pytest.mark.parametrize("data,filename", [
	(b"<html><script>alert(1)</script></html>", "evidence.png"),
	(make_image(), "evidence.svg"),
], ids=["not-an-image", "wrong-extension"])
def test_report_with_invalid_attachment(client, data, filename):
	login_as(client, create_user("reporter"))

	rv = client_request(client, "POST", "/report/", content_type="multipart/form-data",
			data=report_form(file_upload=(io.BytesIO(data), filename)))

	assert rv.status_code == 200
	html = rv.data.decode("utf-8")
	assert "actually an image" in html or "Please upload a PNG" in html
	db.session.expire_all()
	assert Report.query.count() == 0
	assert ReportAttachment.query.count() == 0
	assert Thread.query.filter(Thread.title.like("Report:%")).count() == 0


def setup_report():
	reporter = create_user("reporter")
	create_user("approver", UserRank.APPROVER)
	create_user("editor", UserRank.EDITOR)
	thread = create_thread(reporter, title="Report: Spam", private=True)
	return create_report(reporter, thread, title="Spam package")


def get_report(report_id: str) -> Report:
	db.session.expire_all()
	report = db.session.get(Report, report_id)
	assert report is not None
	return report


def last_reply(report: Report) -> ThreadReply:
	return report.thread.replies.all()[-1]


def as_user(client, username: str):
	login_as(client, User.query.filter_by(username=username).one())


@pytest.mark.parametrize("username,status", [
	(None, 404),
	("reporter", 404),
	("approver", 404),
	("editor", 200),
])
def test_view_report(client, username, status):
	report = setup_report()
	if username:
		as_user(client, username)

	rv = client_request(client, "GET", f"/admin/reports/{report.id}/")
	assert rv.status_code == status
	assert ("Spam package" in rv.data.decode("utf-8")) == (status == 200)


@pytest.mark.parametrize("username,status", [
	("reporter", 403),
	("approver", 403),
	("editor", 200),
])
def test_list_reports(client, username, status):
	setup_report()
	as_user(client, username)

	rv = client_request(client, "GET", "/admin/reports/")
	assert rv.status_code == status
	assert ("Spam package" in rv.data.decode("utf-8")) == (status == 200)


@pytest.mark.parametrize("button,outcome", [
	("completed", "as completed"),
	("removed", "as content removed"),
	("invalid", "without action"),
])
def test_resolve_and_reopen_report(client, button, outcome):
	report = setup_report()
	as_user(client, "editor")
	url = f"/admin/reports/{report.id}/"

	rv = client_request(client, "POST", url, data={button: "1"})
	assert rv.status_code == 200
	report = get_report(report.id)
	assert report.is_resolved
	assert AuditLogEntry.query.filter_by(title=f"Report closed {outcome} \"Spam package\"").count() == 1
	assert last_reply(report).comment == f"Closed report {outcome}"
	assert last_reply(report).is_status_update

	rv = client_request(client, "POST", url, data={"reopen": "1"})
	assert rv.status_code == 200
	report = get_report(report.id)
	assert not report.is_resolved
	assert AuditLogEntry.query.filter_by(title="Reopened report \"Spam package\"").count() == 1
	assert last_reply(report).comment == "Reopened report"


def test_resolve_report_without_outcome(client):
	report = setup_report()
	as_user(client, "editor")

	rv = client_request(client, "POST", f"/admin/reports/{report.id}/", data={})

	assert rv.status_code == 400
	assert not get_report(report.id).is_resolved


@pytest.mark.parametrize("username", ["reporter", "approver"])
def test_resolve_report_no_permission(client, username):
	report = setup_report()
	as_user(client, username)

	rv = client_request(client, "POST", f"/admin/reports/{report.id}/", data={"completed": "1"})

	assert rv.status_code == 404
	assert not get_report(report.id).is_resolved


@pytest.mark.parametrize("username,status", [
	("reporter", 404),
	("approver", 404),
	("editor", 302),
])
def test_edit_report(client, username, status):
	report = setup_report()
	as_user(client, username)

	rv = client_request(client, "POST", f"/admin/reports/{report.id}/edit/",
			data=report_form(title="Edited report title"))

	assert rv.status_code == status
	report = get_report(report.id)
	assert (report.title == "Edited report title") == (status == 302)
	assert AuditLogEntry.query.filter_by(title="Edited report \"Edited report title\"").count() == (1 if status == 302 else 0)
