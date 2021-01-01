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
			syntax_error("No value given")

		key = key_value[0].strip()
		if key == "":
			syntax_error("Empty key")

		value = key_value[1].strip()
		if value == "":
			syntax_error("Empty value")

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
