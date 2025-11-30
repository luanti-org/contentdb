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
