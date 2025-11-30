# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Optional

import requests

from app import app
from app.models import User
from app.tasks import celery


@celery.task()
def post_discord_webhook(username: Optional[str], content: str, is_queue: bool, title: Optional[str] = None, description: Optional[str] = None, thumbnail: Optional[str] = None):
	discord_urls = app.config.get("DISCORD_WEBHOOK_QUEUE" if is_queue else "DISCORD_WEBHOOK_FEED")
	if discord_urls is None:
		return

	if isinstance(discord_urls, str):
		discord_urls = [discord_urls]

	json = {
		"content": content[0:2000],
	}

	if username:
		json["username"] = username[0:80]
		user = User.query.filter_by(username=username).first()
		if user:
			json["avatar_url"] = user.get_profile_pic_url().replace("/./", "/")
			if json["avatar_url"].startswith("/"):
				json["avatar_url"] = app.config["BASE_URL"] + json["avatar_url"]

	if title:
		embed = {
			"title": title[0:256],
			"description": description[0:4000],
		}

		if thumbnail:
			embed["thumbnail"] = {"url": thumbnail}

		json["embeds"] = [embed]

	for url in discord_urls:
		res = requests.post(url, json=json, headers={"Accept": "application/json"})
		if not res.ok:
			raise Exception(f"Failed to submit Discord webhook {res.json}")
		res.raise_for_status()
