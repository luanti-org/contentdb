# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 rubenwardy <rw@rubenwardy>

from typing import Optional

from app.models import User, PackageRelease, AuditSeverity
from app.utils.flask import abs_url
from app.utils.models import add_system_audit_log


# Shown to the user instead of the reason, so that the checks can't be probed
REJECTED_MESSAGE = "This release was rejected, please contact staff"


def report_malicious_content(causer: Optional[User], release: PackageRelease, reason: str) -> str:
	"""
	Handles content that can't be made by accident, such as a zip with path traversal, by recording it in the audit log.

	The caller must commit, and should then send the returned Discord message to the staff queue.

	The reason isn't shown to the user, so that the checks can't be probed. Show REJECTED_MESSAGE instead.

	:returns: the Discord message
	"""
	package = release.package
	audit_url = release.get_edit_url()
	links = "\n".join([abs_url(package.get_url("packages.view")), abs_url(audit_url)])

	# Not attached to the package, as maintainers can see the package's audit log
	add_system_audit_log(AuditSeverity.MODERATION, f"Malicious content detected: {reason}", audit_url, None,
			f"{reason}\n\n{links}")

	causer_desc = causer.username if causer else "unknown"
	discord_message = (f":warning: Malicious content detected in release {release.title} of {package.get_id()}, "
			f"triggered by {causer_desc}\n"
			f"Reason: {reason}\n{links}")

	return discord_message
