# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from enum import Enum


class LuantiCheckError(Exception):
	def __init__(self, value):
		self.value = value

	def __str__(self):
		return repr("Error validating package: " + self.value)


class ContentType(Enum):
	UNKNOWN = "unknown"
	MOD = "mod"
	MODPACK = "modpack"
	GAME = "game"
	TXP = "texture pack"

	def is_mod_like(self):
		return self == ContentType.MOD or self == ContentType.MODPACK

	def validate_same(self, other):
		"""
		Whether `other` is an acceptable type for this
		"""
		assert other

		if self == ContentType.MOD:
			if not other.is_mod_like():
				raise LuantiCheckError("Expected a mod or modpack, found " + other.value)

		elif self == ContentType.TXP:
			if other != ContentType.UNKNOWN and other != ContentType.TXP:
				raise LuantiCheckError("expected a " + self.value + ", found a " + other.value)

		elif other != self:
			raise LuantiCheckError("Expected a " + self.value + ", found a " + other.value)


from .tree import PackageTreeNode, get_base_dir


def build_tree(path, expected_type=None, author=None, repo=None, name=None, strict: bool = True):
	path = get_base_dir(path)

	root = PackageTreeNode(path, "/", author=author, repo=repo, name=name, strict=strict)
	assert root

	if expected_type:
		expected_type.validate_same(root.type)

	return root
