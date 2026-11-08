# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
User markdown must not be able to run scripts. The rules are in app/markdown/cleaner.py.
"""

from html.parser import HTMLParser
from urllib.parse import urlparse

import pytest

from app.markdown import render_markdown


SAFE_TAGS = {"p", "a", "img", "code", "pre", "div", "span", "details", "summary", "br"}
SAFE_ATTRIBUTES = {"href", "src", "alt", "title", "rel", "class"}
SAFE_SCHEMES = {"", "http", "https", "mailto"}


class ElementCollector(HTMLParser):
	def __init__(self):
		super().__init__()
		self.elements: list[tuple[str, dict[str, str | None]]] = []

	def handle_starttag(self, tag, attrs):
		self.elements.append((tag, dict(attrs)))


def find_dangerous(html: str) -> list[str]:
	"""
	Parses the output as a browser would, and lists anything that could run a script.
	"""
	parser = ElementCollector()
	parser.feed(html)
	problems = []
	for tag, attrs in parser.elements:
		if tag not in SAFE_TAGS:
			problems.append(f"tag {tag}")
		for name, value in attrs.items():
			if name not in SAFE_ATTRIBUTES:
				problems.append(f"attribute {name} on {tag}")
			elif name in ("href", "src"):
				scheme = urlparse((value or "").strip()).scheme.lower()
				if scheme not in SAFE_SCHEMES:
					problems.append(f"{scheme}: URL in {name} on {tag}")
	return problems


@pytest.mark.parametrize("source", [
	"<script>alert(1)</script>",
	"<SCRIPT SRC=https://evil.example/x.js></SCRIPT>",
	"Hello <script>alert(1)</script> world",
	"[click](javascript:alert(1))",
	"[click](JaVaScRiPt:alert(1))",
	"[click](  javascript:alert(1))",
	"[click](java&#x09;script:alert(1))",
	"[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
	"[click](vbscript:msgbox(1))",
	"<a href=\"javascript:alert(1)\">click</a>",
	"![img](javascript:alert(1))",
	"<img src=x onerror=alert(1)>",
	"<img src=\"https://example.com/a.png\" onload=\"alert(1)\">",
	"<p onclick=\"alert(1)\">text</p>",
	"<a href=\"https://example.com\" onmouseover=\"alert(1)\">link</a>",
	"<svg onload=alert(1)><circle r=10></circle></svg>",
	"<iframe src=\"https://evil.example\"></iframe>",
	"<object data=\"https://evil.example/x.swf\"></object>",
	"<embed src=\"https://evil.example/x.swf\">",
	"<style>body { display: none }</style>",
	"<form action=\"https://evil.example\"><input name=password></form>",
	"<div style=\"background: url(javascript:alert(1))\">x</div>",
	"<details open ontoggle=alert(1)><summary>x</summary></details>",
	"[a]: javascript:alert(1)\n\n[click][a]",
	"<https://example.com\" onmouseover=\"alert(1)>",
])
def test_dangerous_markdown_is_cleaned(source):
	html = render_markdown(source)
	assert find_dangerous(html) == [], html


@pytest.mark.parametrize("source,expected", [
	("[link](https://example.com)", 'href="https://example.com"'),
	("[link](http://example.com)", 'href="http://example.com"'),
	("[mail](mailto:a@example.com)", 'href="mailto:a@example.com"'),
	("![img](https://example.com/a.png)", 'src="https://example.com/a.png"'),
])
def test_safe_links_kept(source, expected):
	assert expected in render_markdown(source)


def test_disallowed_tags_are_escaped_not_removed():
	html = render_markdown("<script>alert(1)</script>")
	assert "&lt;script&gt;" in html


def test_disallowed_style_attribute_removed():
	html = render_markdown('<span style="color: red" class="evil">x</span>')
	assert "style" not in html
	assert "evil" not in html


def test_code_blocks_are_not_linkified():
	html = render_markdown("```\nhttps://example.com\n```\n\n`https://example.org`")
	assert "<a" not in html
	assert "https://example.com" in html
	assert "https://example.org" in html


def test_code_block_html_is_escaped():
	html = render_markdown("```html\n<script>alert(1)</script>\n```")
	assert find_dangerous(html) == [], html
	assert "&lt;" in html
