#!/usr/bin/python

import subprocess
from typing import List

import requests


base_url = "https://content.luanti.org"
translations = []


def add_translations_from_api_array(context: str, path: str, fields: List[str]):
	print(f"Extracting translations from {path}")
	url = base_url + path
	req = requests.get(url)
	json = req.json()
	for i, row in enumerate(json):
		for field in fields:
			if row.get(field) is not None:
				hint = f"{context}: {field} for {row['name']}"
				translations.append((context, hint, row[field]))


add_translations_from_api_array("tags", "/api/tags/", ["title", "description"])
add_translations_from_api_array("content_warnings", "/api/content_warnings/", ["title", "description"])


with open("app/_translations.py", "w") as f:
	f.write("# THIS FILE IS AUTOGENERATED: utils/extract_translations.py\n\n")
	f.write("from flask_babel import pgettext\n\n")
	for (context, hint, translation) in translations:
		escaped = translation.replace('\n', '\\n').replace("\"", "\\\"")
		if hint:
			f.write(f"# NOTE: {hint}\n")
		f.write(f"pgettext(\"{context}\", \"{escaped}\")\n")


subprocess.run(["pybabel", "extract", "-F", "babel.cfg", "-k", "lazy_gettext", "-o", "translations/messages.pot", "-c", "NOTE", "."])
subprocess.run(["pybabel", "update", "-i", "translations/messages.pot", "-d", "translations", "--no-fuzzy-matching"])
