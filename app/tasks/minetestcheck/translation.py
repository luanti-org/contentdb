# ContentDB
# Copyright (C) 2024 rubenwardy
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

import os
import re


class Translation:
	language: str
	textdomain: str
	entries: dict[str]

	def __init__(self, language: str, textdomain: str, entries: dict):
		self.language = language
		self.textdomain = textdomain
		self.entries = entries



def parse_tr(filepath: str) -> Translation:
	entries = {}
	filename = os.path.basename(filepath)
	filename_parts = filename.split(".")

	assert len(filename_parts) >= 3
	assert filename_parts[-1] == "tr"
	language = filename_parts[-2]
	textdomain = ".".join(filename_parts[0:-2])

	with open(filepath, "r", encoding='utf-8') as existing_file:
		lines = existing_file.readlines()
		line_index = 0
		while line_index < len(lines):
			line = lines[line_index].rstrip('\n')

			if line == "":
				pass

			# Comment lines
			elif line.startswith("#"):
				# Store first occurrence of textdomain
				# discard all subsequent textdomain lines
				if line.startswith("# textdomain:"):
					line_textdomain = line[13:].strip()
					if line_textdomain != textdomain:
						raise SyntaxError(
							f"Line {line_index + 1}: The filename's textdomain ({textdomain}) should match the comment ({line_textdomain})")
			else:
				i = 0
				had_equals = False
				source = ""
				current_part = ""
				while i < len(line):
					if line[i] == "@":
						if i + 1 < len(line):
							i += 1
							code = line[i]
							if code == "=":
								current_part += "="
							elif code == "@":
								current_part += "@"
							elif code == "n":
								current_part += "\n"
							elif code.isdigit():
								current_part += "@" + code
							else:
								raise SyntaxError(f"Line {line_index + 1}: Unknown escape character: {code}")

						else:
							# @\n -> add new line
							line_index += 1
							if line_index >= len(lines):
								raise SyntaxError(f"Line {line_index + 1}: Unexpected end of file")
							line = lines[line_index]
							current_part += "\n"
							i = 0
							continue
					elif not had_equals and line[i] == "=":
						had_equals = True
						source = current_part
						current_part = ""

					else:
						current_part += line[i]

					i += 1

				translation = current_part
				if not had_equals:
					raise SyntaxError(f"Line {line_index + 1}: Missing = in line")

				entries[source.strip()] = translation.strip()

			line_index += 1

	return Translation(language, textdomain, entries)
