# Copyright (c) 2016  Andrew "rubenwardy" Ward
# License: MIT
# Source: https://github.com/rubenwardy/python_phpbb_parser

import re
import sys
import urllib
import urllib.parse as urlparse
import urllib.request
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag


def url_encode_non_ascii(b):
	return re.sub('[\x80-\xFF]', lambda c: '%%%02x' % ord(c.group(0)), b)


class Profile:
	def __init__(self, username):
		self.username   = username
		self.signature  = ""
		self.avatar     = None
		self.properties = {}

	def set(self, key, value):
		self.properties[key.lower()] = value

	def get(self, key):
		return self.properties.get(key.lower())

	def __str__(self):
		return self.username + "\n" + str(self.signature) + "\n" + str(self.properties)


def __extract_properties(profile, soup):
	el = soup.find(id="viewprofile")
	if el is None:
		return None

	res1 = el.find_all("dl")
	imgs = res1[0].find_all("img")
	if len(imgs) == 1:
		profile.avatar = imgs[0]["src"]

	res = el.select("dl.left-box.details")
	if len(res) != 1:
		return None

	catch_next_key = None

	# Look through
	for element in res[0].children:
		if element.name == "dt":
			if catch_next_key is None:
				catch_next_key = element.text.lower()[:-1].strip()
			else:
				print("Unexpected dt!")

		elif element.name == "dd":
			if catch_next_key is None:
				print("Unexpected dd!")
			else:
				if catch_next_key != "groups":
					profile.set(catch_next_key, element.text)
				catch_next_key = None

		elif element and element.name is not None:
			print("Unexpected other")


def __extract_signature(soup):
	res = soup.find_all("div", class_="signature")
	if len(res) != 1:
		return None
	else:
		return str(res[0])


def get_profile_url(url, username):
	url = urlparse.urlparse(url)

	# Update path
	url = url._replace(path="/memberlist.php")

	# Set query args
	query = dict(urlparse.parse_qsl(url.query))
	query.update({ "un": username, "mode": "viewprofile" })
	query_encoded = urlencode(query)
	url = url._replace(query=query_encoded)

	return urlparse.urlunparse(url)


def get_profile(url, username):
	url = get_profile_url(url, username)

	try:
		req = urllib.request.urlopen(url, timeout=15)
	except urllib.error.HTTPError as e:
		if e.code == 404:
			return None

		raise IOError(e)

	contents = req.read().decode("utf-8")
	soup = BeautifulSoup(contents, "lxml")
	if soup is None:
		return None

	profile = Profile(username)
	profile.signature = __extract_signature(soup)
	__extract_properties(profile, soup)

	return profile


regex_id = re.compile(r"^.*t=([0-9]+).*$")


def _find(el: Tag, *args: Any, **kwargs: Any) -> Tag:
	res = el.find(*args, **kwargs)
	assert isinstance(res, Tag), "Unexpected forum page layout"
	return res


def _match_topic_id(href: str) -> str:
	m = regex_id.match(href)
	assert m is not None, f"Unable to get topic id from {href}"
	return m.group(1)


def parse_forum_list_page(id, page, out, extra=None):
	num_per_page = 30
	start = page*num_per_page+1
	print(" - Fetching page {} (topics {}-{})".format(page, start, start+num_per_page), file=sys.stderr)

	url = "https://forum.luanti.org/viewforum.php?f=" + str(id) + "&start=" + str(start)
	r = urllib.request.urlopen(url).read().decode("utf-8")
	soup = BeautifulSoup(r, "html.parser")

	for row in soup.find_all("li", class_="row"):
		classes = row.get_attribute_list("class")
		if "sticky" in classes or "announce" in classes or "global-announce" in classes:
			continue

		topic = _find(row, "dl")

		# Link info
		link   = _find(topic, class_="topictitle")
		id	   = _match_topic_id(str(link.get("href")))
		title  = link.find(text=True)

		# Date
		left   = _find(topic, class_="topic-poster")
		date_text = _find(left, "time").get_text()
		date   = datetime.strptime(date_text, "%a %b %d, %Y %H:%M")
		links  = left.find_all("a")
		if len(links) == 0:
			continue

		author = links[-1].get_text().strip()

		# Get counts
		posts  = _find(topic, class_="posts").find(text=True)
		views  = _find(topic, class_="views").find(text=True)

		if id in out:
			print("   - got {} again, title: {}".format(id, title), file=sys.stderr)
			assert title == out[id]['title']
			return False

		entry: dict[str, Any] = {
			"id"    : id,
			"title" : title,
			"author": author,
			"posts" : posts,
			"views" : views,
			"date"  : date
		}

		if extra is not None:
			for key, value in extra.items():
				entry[key] = value

		out[id] = entry

	return True


def get_topics_from_forum(id, out, extra=None):
	print("Fetching all topics from forum {}".format(id), file=sys.stderr)
	page = 0
	while parse_forum_list_page(id, page, out, extra):
		page = page + 1

	return out
