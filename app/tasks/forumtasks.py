# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import json
import re
import sys
import urllib.request
from typing import Optional
from urllib.parse import urljoin

from sqlalchemy import or_

from app.models import User, db, PackageType, ForumTopic
from app.tasks import celery
from app.utils.user import make_valid_username
from app.utils.phpbbparser import get_profile, get_topics_from_forum
from .usertasks import set_profile_picture_from_url, update_github_user_id_raw


def _get_or_create_user(forums_username: str, cache: Optional[dict] = None) -> Optional[User]:
	if cache:
		user = cache.get(forums_username)
		if user:
			return user

	user = User.query.filter_by(forums_username=forums_username).first()
	if user is None:
		cdb_username = make_valid_username(forums_username)
		user = User.query.filter(or_(User.username == cdb_username, User.forums_username == cdb_username)).first()
		if user:
			return None

		user = User(cdb_username)
		user.forums_username = forums_username
		user.display_name = forums_username
		db.session.add(user)

	if cache:
		cache[forums_username] = user
	return user


@celery.task()
def check_forum_account(forums_username, force_replace_pic=False):
	print("### Checking " + forums_username, file=sys.stderr)
	try:
		profile = get_profile("https://forum.luanti.org", forums_username)
	except OSError as e:
		print(e, file=sys.stderr)
		return

	if profile is None:
		return

	user = _get_or_create_user(forums_username)
	if user is None:
		return

	needs_saving = False

	# Get GitHub username
	github_username = profile.get("github")
	if github_username is not None and github_username.strip() != "":
		print("Updated GitHub username for " + user.display_name + " to " + github_username, file=sys.stderr)
		user.github_username = github_username
		update_github_user_id_raw(user)
		needs_saving = True

	pic = profile.avatar
	if pic and pic.startswith("http"):
		pic = None

	# Save
	if needs_saving:
		db.session.commit()

	if pic:
		pic = urljoin("https://forum.luanti.org/", pic)
		print(f"####### Picture: {pic}", file=sys.stderr)
		print(f"####### User pp {user.profile_pic}", file=sys.stderr)

		pic_needs_replacing = user.profile_pic is None or user.profile_pic == "" or \
				user.profile_pic.startswith("https://forum.luanti.org") or force_replace_pic
		if pic_needs_replacing and pic.startswith("https://forum.luanti.org"):
			print(f"####### Queueing", file=sys.stderr)
			set_profile_picture_from_url.delay(user.username, pic)

	return needs_saving


@celery.task()
def check_all_forum_accounts():
	query = User.query.filter(User.forums_username.isnot(None))
	for user in query.all():
		check_forum_account(user.forums_username)


regex_tag    = re.compile(r"\[([a-z0-9_]+)\]")
BANNED_NAMES = ["mod", "game", "old", "outdated", "wip", "api", "beta", "alpha", "git"]


def get_name_from_taglist(taglist):
	for tag in reversed(regex_tag.findall(taglist)):
		if len(tag) < 30 and not tag in BANNED_NAMES and \
				not re.match(r"^[a-z]?[0-9]+$", tag):
			return tag

	return None


regex_title = re.compile(r"^((?:\[[^\]]+\] *)*)([^\[]+) *((?:\[[^\]]+\] *)*)[^\[]*$")


def parse_title(title):
	m = regex_title.match(title)
	if m is None:
		print("Invalid title format: " + title, file=sys.stderr)
		return title, get_name_from_taglist(title)
	else:
		return m.group(2).strip(), get_name_from_taglist(m.group(3))


def get_links_from_mod_search():
	links = {}

	try:
		contents = urllib.request.urlopen("https://krock-works.uk.to/minetest/modList.php").read().decode("utf-8")
		for x in json.loads(contents):
			try:
				link = x.get("link")
				if link is not None:
					links[int(x["topicId"])] = link
			except ValueError:
				pass

	except urllib.error.URLError:
		print("Unable to open krocks mod search!", file=sys.stderr)
		return links

	return links


@celery.task()
def import_topic_list():
	links_by_id = get_links_from_mod_search()

	info_by_id = {}
	get_topics_from_forum(15, out=info_by_id, extra={'type': PackageType.GAME, 'wip': False})
	get_topics_from_forum(50, out=info_by_id, extra={'type': PackageType.GAME, 'wip': True})
	get_topics_from_forum(11, out=info_by_id, extra={'type': PackageType.MOD, 'wip': False})
	get_topics_from_forum(9, out=info_by_id, extra={'type': PackageType.MOD, 'wip': True})
	get_topics_from_forum(4, out=info_by_id, extra={'type': PackageType.TXP, 'wip': False})

	# Caches
	username_to_user = {}
	topics_by_id     = {}
	for topic in ForumTopic.query.all():
		if topic.topic_id in info_by_id:
			topics_by_id[topic.topic_id] = topic
		else:
			db.session.delete(topic)
			print(f"Deleting topic {topic.topic_id} title {topic.title}", file=sys.stderr)

	username_conflicts = set()

	# Create or update
	for info in info_by_id.values():
		id = int(info["id"])

		# Get author
		username = info["author"]
		user = _get_or_create_user(username, username_to_user)
		if user is None:
			username_conflicts.add(username)
			continue

		# Get / add row
		topic = topics_by_id.get(id)
		if topic is None:
			topic = ForumTopic()
			db.session.add(topic)

		# Parse title
		title, name = parse_title(info["title"])

		# Get link
		link = links_by_id.get(id)

		# Fill row
		topic.topic_id   = int(id)
		topic.author     = user
		topic.type       = info["type"]
		topic.title      = title
		topic.name       = name
		topic.link       = link
		topic.wip        = info["wip"]
		topic.posts      = int(info["posts"])
		topic.views      = int(info["views"])
		topic.created_at = info["date"]

	db.session.commit()

	if len(username_conflicts) > 0:
		print("The following forum usernames could not be created: " + (", ".join(username_conflicts)))
