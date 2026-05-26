# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Sequence
from bs4 import BeautifulSoup
from jinja2.utils import markupsafe
from markdown_it import MarkdownIt
from markdown_it.common.utils import unescapeAll, escapeHtml
from markdown_it.token import Token
from markdown_it.presets import gfm_like
from mdit_py_plugins.anchors import anchors_plugin
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound
from pygments.formatters.html import HtmlFormatter

from .cleaner import clean_html
from .mention import init_mention


def highlight_code(code, name, attrs):
	try:
		lexer = get_lexer_by_name(name)
	except ClassNotFound:
		return None

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

md_with_anchors = MarkdownIt("gfm-like", {"highlight": highlight_code})
md_with_anchors.use(anchors_plugin, permalink=True, permalinkSymbol="🔗", max_level=6)
md_with_anchors.add_render_rule("fence", render_code)
md_with_anchors.linkify.set({"fuzzy_link": False})
init_mention(md_with_anchors)

md_no_anchors = MarkdownIt("gfm-like", {"highlight": highlight_code})
md_no_anchors.add_render_rule("fence", render_code)
md_no_anchors.linkify.set({"fuzzy_link": False})
init_mention(md_no_anchors)

def render_markdown(source, clean=True, remove_headings=False):
	md = md_no_anchors if remove_headings else md_with_anchors
	html = md.render(source)
	if remove_headings:
		html = replace_headings(html)
	if clean:
		html = clean_html(html)
	return html

def init_markdown(app):
	@app.template_filter()
	def markdown(source, remove_headings=False):
		return markupsafe.Markup(render_markdown(source, remove_headings=remove_headings))

def replace_headings(html: str):
	soup = BeautifulSoup(html, "html.parser")

	for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
		p = soup.new_tag("p")
		strong = soup.new_tag("strong")
		strong.string = tag.get_text()
		p.append(strong)
		tag.replace_with(p)

	return str(soup)

def get_headings(html: str):
	soup = BeautifulSoup(html, "html.parser")
	headings = soup.find_all(["h1", "h2", "h3"])

	root = []
	stack = []
	for heading in headings:
		text = heading.find(text=True, recursive=False)
		this = {"link": heading.get("id") or "", "text": text, "children": []}
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


def get_links(html: str) -> set:
	soup = BeautifulSoup(html, "html.parser")
	links = soup.select("a[href]")
	return set([x.get("href") for x in links])
