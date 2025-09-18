# ContentDB
# Copyright (C) rubenwardy
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

from html.parser import HTMLParser
import re
import sys
from urllib.parse import urljoin

from flask_babel import gettext

from app.markdown import render_markdown
from app.models import Package, PackageType, PackageReview
from app.utils import abs_url_for


def normalize_whitespace(x):
	return re.sub(r"\s+", " ", x)


assert normalize_whitespace(" one  three\nfour\n\n") == " one three four "


# Styles and custom tags
HEAD = normalize_whitespace("""
	<tag name=code color=#7bf font=mono>
	<tag name=action color=#4CDAFA hovercolor=#97EAFC>
""").strip()


def escape_hypertext(text):
	return text.replace("\\", "\\\\").replace("<", "\\<").replace(">", "\\>")


def get_attributes(attrs):
	retval = {}
	for attr in attrs:
		retval[attr[0]] = attr[1]
	return retval


def make_indent(w):
	return f"<img name=blank.png width={16*w} height=1>"


class MinetestHTMLParser(HTMLParser):
	def __init__(self, page_url: str, include_images: bool, link_prefix: str):
		super().__init__()
		self.page_url = page_url
		self.include_images = include_images
		self.link_prefix = link_prefix

		self.completed_text = ""
		self.current_line = ""
		self.last_id = None
		self.links = {}
		self.images = {}
		self.image_tooltips = {}
		self.is_preserving = False
		self.remove_until = None
		self.indent_level = 0

	def finish_line(self):
		self.completed_text += self.current_line.rstrip() + "\n"
		self.current_line = ""

	def resolve_url(self, url: str) -> str:
		if self.page_url == "":
			return url
		else:
			return urljoin(self.page_url, url)

	def handle_starttag(self, tag, attrs):
		if self.is_preserving or self.remove_until:
			return

		attr_by_name = get_attributes(attrs)
		self.last_id = get_attributes(attrs).get("id", self.last_id)

		if tag == "p":
			pass
		elif tag == "pre":
			self.current_line += "<code>"
			self.is_preserving = True
		elif tag == "table":
			# Tables are currently unsupported and removed
			self.remove_until = "table"

			url = self.page_url
			if self.last_id is not None:
				url = url + "#" + self.last_id

			name = f"{self.link_prefix}{len(self.links)}"
			self.links[name] = url
			self.current_line += f"<action name={name}><u>"
			self.current_line += escape_hypertext(gettext("(view table in browser)"))
			self.current_line += "</u></action>"
			self.finish_line()
		elif tag == "br":
			self.finish_line()
		elif tag == "h1" or tag == "h2":
			self.finish_line()
			self.current_line += "<big>"
		elif tag == "h3" or tag == "h4" or tag == "h5":
			self.finish_line()
			self.current_line += "<b>"
		elif tag == "a":
			if "href" in attr_by_name:
				name = f"{self.link_prefix}{len(self.links)}"
				self.links[name] = self.resolve_url(attr_by_name["href"])
				self.current_line += f"<action name={name}><u>"
			else:
				self.current_line += "<action><u>"
		elif tag == "img":
			if "src" in attr_by_name:
				name = f"image_{len(self.images)}"
				if self.include_images:
					self.images[name] = self.resolve_url(attr_by_name["src"])
					width = attr_by_name.get("width", 128)
					height = attr_by_name.get("height", 128)
					self.current_line += f"<img name={name} width={width} height={height}>"

					if "alt" in attr_by_name:
						self.image_tooltips[name] = attr_by_name["alt"]
				else:
					self.links[name] = self.resolve_url(attr_by_name["src"])
					label = gettext("Image")
					if "alt" in attr_by_name:
						label = f"{label}: {attr_by_name['alt']}"
					self.current_line += f"<action name={name}><u>{escape_hypertext(label)}</u></action>"
		elif tag == "b" or tag == "strong":
			self.current_line += "<b>"
		elif tag == "i" or tag == "em":
			self.current_line += "<i>"
		elif tag == "u":
			self.current_line += "<u>"
		elif tag == "li":
			if self.current_line.strip() != "":
				self.finish_line()
			else:
				self.current_line = ""

			self.current_line += make_indent(self.indent_level) + "• "
		elif tag == "code":
			self.current_line += "<code>"
		elif tag == "span":
			pass
		elif tag == "ul":
			self.indent_level += 1
		else:
			print("UNKNOWN TAG ", tag, attrs, file=sys.stderr)

	def handle_endtag(self, tag):
		if self.remove_until:
			if self.remove_until == tag:
				self.remove_until = None
			return

		if tag == "pre":
			self.current_line = self.current_line.rstrip() + "</code>"
			self.finish_line()
			self.is_preserving = False
		elif self.is_preserving:
			return
		elif tag == "p":
			self.current_line = self.current_line.rstrip()
			self.finish_line()
		elif tag == "h1" or tag == "h2":
			self.current_line += "</big>"
			self.finish_line()
		elif tag == "h3" or tag == "h4" or tag == "h5":
			self.current_line += "</b>"
			self.finish_line()
		elif tag == "a":
			self.current_line += "</u></action>"
		elif tag == "code":
			self.current_line += "</code>"
		elif tag == "b" or tag == "strong":
			self.current_line += "</b>"
		elif tag == "i" or tag == "em":
			self.current_line += "</i>"
		elif tag == "u":
			self.current_line += "</u>"
		elif tag == "li":
			self.finish_line()
		elif tag == "ul":
			self.indent_level = max(self.indent_level - 1, 0)

	def handle_data(self, data):
		if self.remove_until:
			return

		if not self.is_preserving:
			data = normalize_whitespace(data)
			if self.current_line.strip() == "":
				data = data.lstrip()

		self.current_line += escape_hypertext(data)

	def handle_entityref(self, name):
		to_value = {
			"lt": "\\<",
			"gr": "\\>",
			"amp": "&",
			"quot": "\"",
			"apos": "'",
		}

		if name in to_value:
			self.current_line += to_value[name]
		else:
			self.current_line += f"&{name};"


def html_to_minetest(html, page_url: str, formspec_version: int = 7, include_images: bool = True, link_prefix: str = "link_"):
	parser = MinetestHTMLParser(page_url, include_images, link_prefix)
	parser.feed(html)
	parser.finish_line()

	return {
		"head": HEAD,
		"body": parser.completed_text.strip() + "\n",
		"links": parser.links,
		"images":  parser.images,
		"image_tooltips": parser.image_tooltips,
	}


def package_info_as_hypertext(package: Package, formspec_version: int = 7):
	links = {}
	body = ""

	def add_value(label, value):
		nonlocal body
		body += f"{label}: <b>{str(value)}</b>\n\n"

	def add_list(label, items):
		nonlocal body

		body += label + ": "
		for i, item in enumerate(items):
			if i != 0:
				body += ", "
			body += f"<b>{str(item)}</b>"

		if len(items) == 0:
			body += "<i>" + gettext("none") + "</i>"

		body += "</b>\n\n"

	add_value(gettext("Type"), package.type.text)
	add_list(gettext("Tags"), [tag.get_translated()["title"] for tag in package.tags])

	if package.type != PackageType.GAME:
		def make_game_link(game):
			key = f"link_{len(links)}"
			links[key] = game.get_url("packages.view", absolute=True)
			return f"<action name={key}><u>{escape_hypertext(game.title)}</u></action>"

		[supported, unsupported] = package.get_sorted_game_support_pair()
		supports_all_games = package.supports_all_games or len(supported) == 0
		if supports_all_games:
			add_value(gettext("Supported Games"), gettext("No specific game required"))
		else:
			add_list(gettext("Supported Games"), [make_game_link(support.game) for support in supported])

		if unsupported and supports_all_games:
			add_list(gettext("Unsupported Games"), [make_game_link(support.game) for support in supported])

	if package.type != PackageType.TXP:
		add_list(gettext("Dependencies"), [x.meta_package.name for x in package.get_sorted_hard_dependencies()])
		add_list(gettext("Optional dependencies"), [x.meta_package.name for x in package.get_sorted_optional_dependencies()])

	languages = [trans.language.title for trans in package.translations]
	languages.insert(0, "English")
	add_list(gettext("Languages"), languages)

	if package.license == package.media_license:
		license = package.license.name
	elif package.type == package.type.TXP:
		license = package.media_license.name
	else:
		license = gettext("%(code_license)s for code,<br>%(media_license)s for media.",
				code_license=package.license.name, media_license=package.media_license.name).replace("<br>", " ")

	add_value(gettext("License"), license)
	if package.dev_state:
		add_value(gettext("Maintenance State"), package.dev_state.value)
	add_value(gettext("Added"), package.created_at.isoformat(timespec="seconds") + "Z")
	add_list(gettext("Maintainers"), [user.display_name for user in package.maintainers])
	add_list(gettext("Provides"), [x.name for x in package.provides])

	return {
		"head": HEAD,
		"body": body,
		"links": links,
		"images":  {},
		"image_tooltips": {},
	}


def package_reviews_as_hypertext(package: Package, formspec_version: int = 7):
	link_counter = 0
	links = {}
	body = ""

	def make_link(url: str, label: str):
		nonlocal link_counter
		link_counter += 1
		links[f"link_{link_counter}"] = url
		return f"<action name=link_{link_counter}>{escape_hypertext(label)}</action>"

	body += make_link(package.get_url("packages.review", absolute=True), gettext("Leave a review"))
	body += "\n\n"

	reviews = package.reviews.all()
	for review in reviews:
		review: PackageReview
		html = render_markdown(review.thread.first_reply.comment)
		content = html_to_minetest(html, package.get_url("packages.view", absolute=True),
				formspec_version, False, f"review_{review.id}_")
		links.update(content["links"])
		comment_body = content["body"].rstrip()

		author = make_link(abs_url_for("users.profile", username=review.author.username), review.author.display_name)
		rating = ["<thumbsdown>", "<thumbsdown>", "<neutral>", "<thumbsup>", "<thumbsup>"][review.rating - 1]
		num_comments = review.thread.replies.count()
		comments = make_link(abs_url_for("threads.view", id=review.thread.id), f"Comments [{num_comments}]")
		positive, negative, _ = review.get_totals()
		helpful = f"Review helpfulness: +{positive} / -{negative}"
		body += f"{author} {rating}\n<big>{escape_hypertext(review.thread.title)}</big>\n{comment_body}\n{comments} — {helpful}\n\n"

	if len(reviews) == 0:
		body += escape_hypertext(gettext("No reviews available."))

	return {
		"head": HEAD,
		"body": body,
		"links": links,
		"images":  {},
		"image_tooltips": {},
	}
