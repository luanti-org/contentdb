# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


class LogicError(Exception):
	def __init__(self, code, message):
		self.code = code
		self.message = message

	def __str__(self):
		return repr("LogicError {}: {}".format(self.code, self.message))
