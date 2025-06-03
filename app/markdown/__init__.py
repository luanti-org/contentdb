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

from typing import Sequence
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from jinja2.utils import markupsafe
from markdown_it import MarkdownIt
from markdown_it.common.utils import unescapeAll, escapeHtml
from markdown_it.token import Token
from markdown_it.presets import gfm_like
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters.html import HtmlFormatter

from .cleaner import clean_html
from .mention import init_mention


def highlight_code(code, name, attrs):
	if name == "":
		return None

	lexer = get_lexer_by_name(name)
	formatter = HtmlFormatter()

	return highlight(code, lexer, formatter)


def render_code(self, tokens: Sequence[Token], idx, options, env):
	token = tokens[idx]
	info = unescapeAll(token.info).strip() if token.info else ""
	langName = info.split(maxsplit=1)[0] if info else ""

	if options.highlight:
		return options.highlight(
			token.content, langName, ""
		) or f"<pre><code>{escapeHtml(token.content)}</code></pre>"

	return f"<pre><code>{escapeHtml(token.content)}</code></pre>"


gfm_like.make()
md = MarkdownIt("gfm-like", {"highlight": highlight_code})
md.add_render_rule("fence", render_code)
init_mention(md)


def render_markdown(source):
	html = md.render(source)
	return clean_html(html)


def init_markdown(app):
	@app.template_filter()
	def markdown(source):
		return markupsafe.Markup(render_markdown(source))


def get_headings(html: str):
	soup = BeautifulSoup(html, "html.parser")
	headings = soup.find_all(["h1", "h2", "h3"])

	root = []
	stack = []
	for heading in headings:
		this = {"link": heading.get("id") or "", "text": heading.text, "children": []}
		this_level = int(heading.name[1:]) - 1

		while this_level <= len(stack):
			stack.pop()

		if len(stack) > 0:
			stack[-1]["children"].append(this)
		else:
			root.append(this)

		stack.append(this)

	return root


def get_user_mentions(html: str) -> set:
	soup = BeautifulSoup(html, "html.parser")
	links = soup.select("a[data-username]")
	return set([x.get("data-username") for x in links])


def get_links(html: str, url: str) -> set:
	soup = BeautifulSoup(html, "html.parser")
	links = soup.select("a[href]")
	return set([urljoin(url, x.get("href")) for x in links])
