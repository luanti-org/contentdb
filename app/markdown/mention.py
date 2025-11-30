# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import re

from flask import url_for
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdown_it.rules_core.state_core import StateCore
from typing import Sequence, List


def render_user_mention(self, tokens: Sequence[Token], idx, options, env):
	token = tokens[idx]
	username = token.content
	url = url_for("users.profile", username=username)
	return f"<a href=\"{url}\" data-username=\"{username}\">@{username}</a>"


def render_package_mention(self, tokens: Sequence[Token], idx, options, env):
	token = tokens[idx]
	username = token.content
	name = token.attrs["name"]
	url = url_for("packages.view", author=username, name=name)
	return f"<a href=\"{url}\">@{username}/{name}</a>"


def parse_mentions(state: StateCore):
	for block_token in state.tokens:
		if block_token.type != "inline" or block_token.children is None:
			continue

		link_depth = 0
		html_link_depth = 0

		children = []
		for token in block_token.children:
			if token.type == "link_open":
				link_depth += 1
			elif token.type == "link_close":
				link_depth -= 1
			elif token.type == "html_inline":
				# is link open / close?
				pass

			if link_depth > 0 or html_link_depth > 0 or token.type != "text":
				children.append(token)
			else:
				children.extend(split_tokens(token, state))

		block_token.children = children


RE_PARTS = dict(
	USER=r"[A-Za-z0-9._-]*\b",
	NAME=r"[A-Za-z0-9_]+\b"
)
MENTION_RE = r"(@({USER})(?:\/({NAME}))?)".format(**RE_PARTS)


def split_tokens(token: Token, state: StateCore) -> List[Token]:
	tokens = []
	content = token.content
	pos = 0
	for match in re.finditer(MENTION_RE, content):
		username = match.group(2)
		package_name = match.group(3)
		(start, end) = match.span(0)

		if start > pos:
			token_text = Token("text", "", 0)
			token_text.content = content[pos:start]
			token_text.level = token.level
			tokens.append(token_text)

		mention = Token("package_mention" if package_name else "user_mention", "", 0)
		mention.content = username
		mention.attrSet("name", package_name)
		mention.level = token.level
		tokens.append(mention)

		pos = end

	if pos < len(content):
		token_text = Token("text", "", 0)
		token_text.content = content[pos:]
		token_text.level = token.level
		tokens.append(token_text)

	return tokens


def init_mention(md: MarkdownIt):
	md.add_render_rule("user_mention", render_user_mention, "html")
	md.add_render_rule("package_mention", render_package_mention, "html")
	md.core.ruler.after("inline", "mention", parse_mentions)
