# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import pytest
from flask import url_for, has_request_context
from sqlalchemy.exc import IntegrityError

from app import app
from app.models import db, User, AuditLogEntry, AuditSeverity
from app.utils.models import get_url_path, add_system_audit_log
from .utils import client # noqa


def add_entry(url):
	user = User.query.filter_by(username="rubenwardy").one()
	db.session.add(AuditLogEntry(user, AuditSeverity.NORMAL, "Test", url))
	db.session.commit()


@pytest.mark.parametrize("url", [None, "/", "/packages/user/name/", "/threads/1/?a=b"])
def test_audit_log_url_allows_paths(client, url):
	add_entry(url)
	assert AuditLogEntry.query.filter_by(title="Test").one().url == url


@pytest.mark.parametrize("url", ["https://content.luanti.org/packages/", "//evil.com/", "packages/", ""])
def test_audit_log_url_rejects_non_paths(client, url):
	with pytest.raises(IntegrityError):
		add_entry(url)

	db.session.rollback()


@pytest.mark.parametrize("url,expected", [
	(None, None),
	("/threads/1/", "/threads/1/"),
	("http://localhost:5124/threads/1/?a=b#c", "/threads/1/?a=b#c"),
	("https://localhost:5124/threads/1/", "/threads/1/"),
	("http://localhost:5124", "/"),
	("HTTPS://LocalHost:5124/threads/1/", "/threads/1/"),
])
def test_get_url_path(client, url, expected):
	assert get_url_path(url) == expected


@pytest.mark.parametrize("url", [
	"https://example.com/threads/1/",
	"https://localhost:5124.example.com/threads/1/",
	"ftp://localhost:5124/threads/1/",
	"//localhost:5124/threads/1/",
	"threads/1/",
	"",
])
def test_get_url_path_rejects_other_urls(client, url):
	with pytest.raises(ValueError):
		get_url_path(url)


def test_get_url_path_uses_server_name(client, monkeypatch):
	monkeypatch.setitem(app.config, "BASE_URL", "https://other.example.com")
	assert get_url_path("http://localhost:5124/threads/1/") == "/threads/1/"
	with pytest.raises(ValueError):
		get_url_path("https://other.example.com/threads/1/")


def test_audit_log_outside_request(client):
	# Like in a task, there's an app context but no request
	assert not has_request_context()
	url = url_for("threads.view", id=1)
	assert url.startswith("http://")

	add_system_audit_log(AuditSeverity.NORMAL, "Test", url)
	assert AuditLogEntry.query.filter_by(title="Test").one().url == "/threads/1/"
