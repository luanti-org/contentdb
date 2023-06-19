# ContentDB
# Copyright (C) 2018-21 rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
import re
import sys
import urllib.request
from urllib.parse import urljoin

from app.models import User, db, PackageType, ForumTopic
from app.tasks import celery
from app.utils import is_username_valid
from app.utils.phpbbparser import get_profile, get_topics_from_forum
from .usertasks import set_profile_picture_from_url


@celery.task()
def check_forum_account(forums_username):
	print("### Checking " + forums_username, file=sys.stderr)
	try:
		profile = get_profile("https://forum.minetest.net", forums_username)
	except OSError as e:
		print(e, file=sys.stderr)
		return

	if profile is None:
		return

	user = User.query.filter_by(forums_username=forums_username).first()

	# Create user
	needs_saving = False
	if user is None:
		user = User(forums_username)
		user.forums_username = forums_username
		db.session.add(user)

	# Get GitHub username
	github_username = profile.get("github")
	if github_username is not None and github_username.strip() != "":
		print("Updated GitHub username for " + user.display_name + " to " + github_username)
		user.github_username = github_username
		needs_saving = True

	pic = profile.avatar
	if pic and pic.startswith("http"):
		pic = None

	# Save
	if needs_saving:
		db.session.commit()

	if pic:
		pic = urljoin("https://forum.minetest.net/", pic)
		print(f"####### Picture: {pic}", file=sys.stderr)
		print(f"####### User pp {user.profile_pic}", file=sys.stderr)

		pic_needs_replacing = user.profile_pic is None or user.profile_pic == "" or \
				user.profile_pic.startswith("https://forum.minetest.net")
		if pic_needs_replacing and pic.startswith("https://forum.minetest.net"):
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
		print("Invalid title format: " + title)
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
		print("Unable to open krocks mod search!")
		return links

	return links


@celery.task()
def import_topic_list():
	links_by_id = get_links_from_mod_search()

	info_by_id = {}
	get_topics_from_forum(11, out=info_by_id, extra={'type': PackageType.MOD, 'wip': False})
	get_topics_from_forum(9, out=info_by_id, extra={'type': PackageType.MOD, 'wip': True})
	get_topics_from_forum(15, out=info_by_id, extra={'type': PackageType.GAME, 'wip': False})
	get_topics_from_forum(50, out=info_by_id, extra={'type': PackageType.GAME, 'wip': True})

	# Caches
	username_to_user = {}
	topics_by_id     = {}
	for topic in ForumTopic.query.all():
		topics_by_id[topic.topic_id] = topic

	def get_or_create_user(username):
		user = username_to_user.get(username)
		if user:
			return user

		if not is_username_valid(username):
			return None

		user = User.query.filter_by(forums_username=username).first()
		if user is None:
			user = User.query.filter_by(username=username).first()
			if user:
				return None

			user = User(username)
			user.forums_username = username
			db.session.add(user)

		username_to_user[username] = user
		return user

	# Create or update
	for info in info_by_id.values():
		id = int(info["id"])

		# Get author
		username = info["author"]
		user = get_or_create_user(username)
		if user is None:
			print("Error! Unable to create user {}".format(username), file=sys.stderr)
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
