# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Permission tables for reports and audit log entries. See permission_tables.py.
"""

from app.models import db, UserRank, Permission, AuditLogEntry, AuditSeverity
from ..factories import create_package, create_report
from ..permission_tables import make_roles, assert_permissions


def test_report(client):
	roles = make_roles({
		"anonymous": None,
		"reporter": UserRank.MEMBER,
		"trusted": UserRank.TRUSTED_MEMBER,
		"curator": UserRank.CURATOR,
		"editor": UserRank.EDITOR,
		"moderator": UserRank.MODERATOR,
		"admin": UserRank.ADMIN,
	})
	report = create_report(roles["reporter"])

	assert_permissions(report, roles, {
		# Reporters see their report through its thread, not the report page
		Permission.SEE_REPORT: {"editor", "moderator", "admin"},
	})

	# The report list and work queue use the global check, which must agree with the report's
	for role, user in roles.items():
		assert Permission.SEE_REPORT.check(user) == report.check_perm(user, Permission.SEE_REPORT), role


def test_audit_log_entry(client):
	roles = make_roles({
		"anonymous": None,
		"member": UserRank.MEMBER,
		"trusted": UserRank.TRUSTED_MEMBER,
		"owner": UserRank.MEMBER,
		"maintainer": UserRank.MEMBER,
		"curator": UserRank.CURATOR,
		"editor": UserRank.EDITOR,
		"moderator": UserRank.MODERATOR,
		"admin": UserRank.ADMIN,
	})
	package = create_package("pkg", roles["owner"], maintainers=[roles["maintainer"]])

	package_entry = AuditLogEntry(roles["admin"], AuditSeverity.EDITOR, "Edited package", "/", package, "Details")
	site_entry = AuditLogEntry(roles["admin"], AuditSeverity.MODERATION, "Changed user", "/", None, "Details")
	db.session.add(package_entry)
	db.session.add(site_entry)
	db.session.commit()

	assert_permissions(package_entry, roles, {
		# Was Approver's, and is now Editor's; Curators don't get it
		Permission.VIEW_AUDIT_DESCRIPTION: {"owner", "maintainer", "editor", "moderator", "admin"},
	}, "package entry")

	assert_permissions(site_entry, roles, {
		Permission.VIEW_AUDIT_DESCRIPTION: {"moderator", "admin"},
	}, "entry without a package")
