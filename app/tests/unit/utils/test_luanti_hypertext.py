# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from app.utils.luanti_hypertext import html_to_luanti


conquer_html = """
<p>
Welcome to <b>Conquer</b>, a mod that adds RTS gameplay. It allows players to start
Conquer sub-games, where they can place buildings, train units, and
fight other players.
</p>

<h2>Starting or joining a session</h2>

<p>
You can list running sessions by typing:
</p>

<pre><code>/conquer list
new line

another new line</code></pre>

<p>
You'll switch into Conquer playing mode, where you will be given buildings that you can place.
You'll need to place a keep, which you must protect at all costs.
</p>

<p>
You may leave a game and return to normal playing mode at anytime by typing:
</p>

<h2>Conquer GUI</h2>

<p>
The Conquer GUI is the central place for monitoring your kingdom.
Once in a session, you can view it by pressing the inventory key (I),
or by punching/right-clicking the keep node.
</p>
"""


conquer_expected = """
Welcome to <b>Conquer</b>, a mod that adds RTS gameplay. It allows players to start Conquer sub-games, where they can place buildings, train units, and fight other players.

<big>Starting or joining a session</big>
You can list running sessions by typing:
<code>/conquer list
new line

another new line</code>
You'll switch into Conquer playing mode, where you will be given buildings that you can place. You'll need to place a keep, which you must protect at all costs.
You may leave a game and return to normal playing mode at anytime by typing:

<big>Conquer GUI</big>
The Conquer GUI is the central place for monitoring your kingdom. Once in a session, you can view it by pressing the inventory key (I), or by punching/right-clicking the keep node.
"""

page_url = "https://example.com/a/b/"


def test_conquer():
	assert html_to_luanti(conquer_html, page_url)["body"].strip() == conquer_expected.strip()


def test_images():
	html = """
		<img src="/path/to/img.png">
	"""

	expected = "<img name=image_0 width=128 height=128>"
	result = html_to_luanti(html, page_url)
	assert result["body"].strip() == expected.strip()
	assert len(result["images"]) == 1
	assert result["images"]["image_0"] == "https://example.com/path/to/img.png"


def test_images_removed():
	html = """
		<img src="/path/to/img.png" alt="alt">
	"""

	expected = "<action name=image_0><u>Image: alt</u></action>"
	result = html_to_luanti(html, page_url, 7, False)
	assert result["body"].strip() == expected.strip()
	assert len(result["images"]) == 0
	assert result["links"]["image_0"] == "https://example.com/path/to/img.png"


def test_links_relative_absolute():
	html = """
		<a href="relative">Relative</a>
		<a href="/absolute">Absolute</a>
		<a href="https://www.minetest.net/downloads/">Other domain</a>
	"""

	expected = "<action name=link_0><u>Relative</u></action> " \
			"<action name=link_1><u>Absolute</u></action> " \
			"<action name=link_2><u>Other domain</u></action>"

	result = html_to_luanti(html, page_url, 7, False)
	assert result["body"].strip() == expected.strip()
	assert result["links"]["link_0"] == "https://example.com/a/b/relative"
	assert result["links"]["link_1"] == "https://example.com/absolute"
	assert result["links"]["link_2"] == "https://www.minetest.net/downloads/"


def test_bullets():
	html = """
		<ul>
			<li>One</li>
			<li>two three<ul><li>sub one</li><li>sub two</li></ul></li>
			<li>four</li>
		</ul>
	"""

	expected = "<img name=blank.png width=16 height=1>• One\n" \
		"<img name=blank.png width=16 height=1>• two three\n" \
		"<img name=blank.png width=32 height=1>• sub one\n" \
		"<img name=blank.png width=32 height=1>• sub two\n\n" \
		"<img name=blank.png width=16 height=1>• four\n"

	result = html_to_luanti(html, page_url)
	assert result["body"].strip() == expected.strip()


def test_table():
	html = """
		<table id="with-id">
			<tr><th>Col A</th><th>Col B</th><th>Col C</th></tr>
			<tr><td>A1</td><td>B1</td><td>C1</td>
			<tr><td>A2</td><td>B2</td><td>C2</td>
			<tr><td>A3</td><td>B3</td><td>C3</td>
		</table>
		<h3 id="heading">Heading</h3> 
		<table>
			<tr><th>Col A</th><th>Col B</th><th>Col C</th></tr>
			<tr><td>A1</td><td>B1</td><td>C1</td>
			<tr><td>A2</td><td>B2</td><td>C2</td>
			<tr><td>A3</td><td>B3</td><td>C3</td>
		</table>
	"""

	expected = "<action name=link_0><u>(view table in browser)</u></action>\n\n" \
			"<b>Heading</b>\n" \
			"<action name=link_1><u>(view table in browser)</u></action>"
	result = html_to_luanti(html, page_url)
	assert result["body"].strip() == expected.strip()
	assert result["links"]["link_0"] == f"{page_url}#with-id"
	assert result["links"]["link_1"] == f"{page_url}#heading"


def test_inline():
	html = """
		<b>One <i>two</i> three</b>
	"""

	expected = "<b>One <i>two</i> three</b>"
	result = html_to_luanti(html, page_url)
	assert result["body"].strip() == expected.strip()


def test_escape():
	html = r"""
		<b>One <i>t\w&lt;o&gt;</i> three</b>
	"""

	expected = r"<b>One <i>t\\w\<o\></i> three</b>"
	result = html_to_luanti(html, page_url)
	assert result["body"].strip() == expected.strip()


def test_unknown_attr():
	html = r"""
		<a href="https://example.com" url="http://www.minetest.net">link</a>
	"""

	expected = r"<action name=link_0><u>link</u></action>"
	result = html_to_luanti(html, page_url)
	assert result["body"].strip() == expected.strip()
