# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 rubenwardy <rw@rubenwardy>

from typing import Optional, Tuple

from app.models import User, Package, PackageRelease, AuditSeverity
from app.utils.flask import abs_url
from app.utils.models import add_system_audit_log


# Shown to the user instead of the reason, so that the checks can't be probed
REJECTED_MESSAGE = "This release was rejected, please contact staff"


def report_malicious_content(causer: Optional[User], package: Optional[Package], release: Optional[PackageRelease],
		reason: str) -> Tuple[str, str]:
	"""
	Handles content that can't be made by accident, such as a zip with path traversal, by recording it in the audit log.

	The caller must commit, and should then send the returned Discord message to the staff queue.

	:returns: (public message, Discord message)
	"""
	audit_url = None
	links = []
	if package:
		audit_url = package.get_url("packages.view")
		links.append(abs_url(audit_url))
	if release:
		audit_url = release.get_edit_url()
		links.append(abs_url(audit_url))
	description = reason + "\n\n" + "\n".join(links)

	# Not attached to the package, as maintainers can see the package's audit log
	add_system_audit_log(AuditSeverity.MODERATION, f"Malicious content detected: {reason}", audit_url, None, description)

	causer_desc = causer.username if causer else "unknown"
	where = f" in {package.get_id()}" if package else ""
	if release:
		where = f" in release {release.title} of {package.get_id()}" if package else f" in release {release.title}"

	discord_message = (f":warning: Malicious content detected{where}, triggered by {causer_desc}\n"
			f"Reason: {reason}\n" + "\n".join(links))

	return REJECTED_MESSAGE, discord_message
