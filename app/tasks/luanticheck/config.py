# ContentDB
# Copyright (C) Lars Mueller
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


def parse_conf(string):
	retval = {}
	lines = string.splitlines()
	i = 0

	def syntax_error(message):
		raise SyntaxError("Line {}: {}".format(i + 1, message))

	while i < len(lines):
		line = lines[i].strip()

		# Comments
		if line.startswith("#") or line == "":
			i += 1
			continue

		key_value = line.split("=", 2)
		if len(key_value) < 2:
			syntax_error("Expected line to contain '='")

		key = key_value[0].strip()
		if key == "":
			syntax_error("Missing key before '='")

		value = key_value[1].strip()
		if value.startswith('"""'):
			value_lines = []
			closed = False
			i += 1
			while i < len(lines):
				value = lines[i]
				if value == '"""':
					closed = True
					value = value[:-3]
					break

				value_lines.append(value)
				i += 1

			if not closed:
				i -= 1
				syntax_error("Unclosed multiline value")

			value_lines.append(value)
			value = "\n".join(value_lines)

		else:
			value = value.rstrip()

		if key in retval:
			syntax_error("Duplicate key {}".format(key))

		retval[key] = value
		i += 1

	return retval
