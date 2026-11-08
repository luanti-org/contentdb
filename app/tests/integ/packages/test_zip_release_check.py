# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
The check_zip_release task, which validates uploaded release zips.
"""

import io
import os
import zipfile

from app import app
from app.models import db, ReleaseState, PackageRelease
from app.tasks.importtasks import check_zip_release
from app.utils.models import get_bot_message_thread
from ..factories import create_user, create_package, create_release


def make_zip(files: dict[str, str]) -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		for name, content in files.items():
			zf.writestr(name, content)
	return buf.getvalue()


def setup_release(data: bytes) -> PackageRelease:
	package = create_package("pkg", create_user("owner"))
	create_release(package, "1.0")
	release = create_release(package, "2.0", approved=False)
	release.state = ReleaseState.PROCESSING
	release.task_id = "pending"
	db.session.commit()

	with open(os.path.join(app.config["UPLOAD_DIR"], os.path.basename(release.upload_path)), "wb") as f:
		f.write(data)
	return release


def run_check(release: PackageRelease):
	result = check_zip_release.apply(args=[release.id])
	db.session.expire_all()
	return result


def test_valid_zip(client):
	release = setup_release(make_zip({
		"pkg/mod.conf": "name = pkg\n",
		"pkg/init.lua": "",
		"pkg/LICENSE.txt": "MIT",
	}))

	result = run_check(release)

	assert result.successful(), result.traceback
	assert release.state == ReleaseState.APPROVED
	assert release.task_id is None
	assert release.file_size_bytes > 0
	assert release.file_sha256 is not None


def test_not_a_zip(client):
	release = setup_release(b"This is not a zip file")

	result = run_check(release)

	assert result.failed()
	assert release.state == ReleaseState.FAILED
	thread = get_bot_message_thread(release.package)
	assert thread is not None
	assert "Release 2.0 validation failed" in thread.replies.all()[-1].comment


def test_invalid_mod(client):
	release = setup_release(make_zip({
		"pkg/mod.conf": "name = wrong_name\n",
		"pkg/init.lua": "",
	}))

	result = run_check(release)

	assert result.failed()
	assert release.state == ReleaseState.FAILED


def test_unsafe_zip(client):
	release = setup_release(make_zip({
		"pkg/mod.conf": "name = pkg\n",
		"pkg/init.lua": "",
		"../../evil.lua": "print('escaped')",
	}))

	result = run_check(release)

	assert result.failed()
	assert "Unsafe zip file" in str(result.result)
	assert release.state == ReleaseState.FAILED
	assert not os.path.exists(os.path.join(os.path.dirname(app.config["UPLOAD_DIR"].rstrip("/")), "evil.lua"))
