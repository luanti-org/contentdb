# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

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
	had_textdomain_comment = False

	with open(filepath, "r", encoding="utf-8") as existing_file:
		lines = existing_file.readlines()
		line_index = 0
		while line_index < len(lines):
			line = lines[line_index].rstrip('\n')

			if line.strip() == "":
				pass

			# Comment lines
			elif line.startswith("#"):
				# Store first occurrence of textdomain
				# discard all subsequent textdomain lines
				if line.startswith("# textdomain:"):
					line_textdomain = line[13:].strip()
					had_textdomain_comment = True
					if line_textdomain != textdomain:
						raise SyntaxError(
							f"Line {line_index + 1}: The filename's textdomain ({textdomain}) should match the comment ({line_textdomain})")

			elif not had_textdomain_comment:
				raise SyntaxError(f"Missing `# textdomain: {textdomain}` at the top of the file")

			else:
				i = 0
				had_equals = False
				source = ""
				current_part = ""
				next_variable = 1
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
								if had_equals:
									if int(code) >= next_variable:
										raise SyntaxError(
											f"Line {line_index + 1}: Unknown argument @{code} in translated string")
								else:
									if int(code) != next_variable:
										raise SyntaxError(
											f"Line {line_index + 1}: Arguments out of order in source, found @{code} and expected @{next_variable}." +
											" Arguments in source must be in increasing order, without gaps or repetitions, starting from 1")

									next_variable += 1
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
