# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import urllib.parse as urlparse
from typing import Optional, Dict, List


def url_set_query(url: str, params: Dict[str, str]) -> str:
	url_parts = list(urlparse.urlparse(url))
	query = dict(urlparse.parse_qsl(url_parts[4]))
	query.update(params)

	url_parts[4] = urlparse.urlencode(query)
	return urlparse.urlunparse(url_parts)


def url_get_query(parsed_url: urlparse.ParseResult) -> Dict[str, List[str]]:
	return urlparse.parse_qs(parsed_url.query)


def get_youtube_id(url: str) -> Optional[str]:
	parsed = urlparse.urlparse(url)
	if (parsed.netloc == "www.youtube.com" or parsed.netloc == "youtube.com") and parsed.path == "/watch":
		video_id = url_get_query(parsed).get("v", [None])[0]
		if video_id:
			return video_id

	elif parsed.netloc == "youtu.be":
		return parsed.path[1:]

	return None


def clean_youtube_url(url: str) -> Optional[str]:
	id_ = get_youtube_id(url)
	if id_:
		return url_set_query("https://www.youtube.com/watch", {"v": id_})

	return None


def get_forum_id(url: str) -> Optional[int]:
	parsed = urlparse.urlparse(url)
	query_params = urlparse.parse_qs(parsed.query)
	values = query_params.get("t")
	try:
		return int(values[0]) if values else None
	except ValueError:
		return None


OAUTH_ALLOWED_CUSTOM_SCHEMES: set[str] = set()
LOCALHOST_NAMES = {"localhost", "127.0.0.1", "::1"}

def is_valid_oauth_redirect_url(url: str) -> bool:
	if "\\" in url or any(ord(c) <= 0x20 or ord(c) == 0x7f for c in url):
		return False

	try:
		parsed = urlparse.urlparse(url)
		hostname = parsed.hostname
	except ValueError:
		return False

	# Codes are added to the query string, a fragment would hide them
	if parsed.fragment or url.endswith("#"):
		return False

	if parsed.scheme in OAUTH_ALLOWED_CUSTOM_SCHEMES:
		return True
	elif parsed.scheme == "https":
		return bool(hostname)
	elif parsed.scheme == "http":
		return hostname in LOCALHOST_NAMES

	return False
