# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

import base64

from app.models import PackageContentDetection


def test_content_as_data_url_encodes_content_data_as_base64_png():
	detection = PackageContentDetection()
	detection.content_data = b"fake-png-bytes"

	url = detection.content_as_data_url

	assert url.startswith("data:image/png;base64,")
	encoded = url[len("data:image/png;base64,"):]
	assert base64.b64decode(encoded) == b"fake-png-bytes"
