# ContentDB
# Copyright (C) 2018-23 rubenwardy
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
