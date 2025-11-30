# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import inspect
import os
import re
import sys
import gzip
import user_agents
from urllib.parse import urlparse, parse_qs, unquote

if not "FLASK_CONFIG" in os.environ:
	os.environ["FLASK_CONFIG"] = "../config.cfg"

logs_dir = sys.argv[1].strip()
if not os.path.isdir(logs_dir):
	sys.exit(1)

# Allow finding the `app` module
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)

from app.models import db, Package, PackageDailyStats

url_re = re.compile(r"\/packages\/([^\/]+)\/([^\/]+)\/releases\/[0-9]+\/download\/[^ ]*")
dt_re = re.compile(r"\[(\d+\/\w+\/[\d: +-]+)\]")
ua_re = re.compile(r"\"([^\"]+)\"$")

row_lookup = {}
package_id_by_key = {}
for package in Package.query.all():
	package_id_by_key[f"{package.author.username}/{package.name}".lower()] = package.id

log_files = [f for f in os.listdir(logs_dir) if os.path.isfile(os.path.join(logs_dir, f))]

ua_is_bot = {}


def my_open(path):
	if path.endswith(".gz"):
		return gzip.open(path, "rt")
	else:
		return open(path, "r")


for log_file in log_files:
	print(f"Importing from {log_file}")
	with my_open(os.path.join(logs_dir, log_file)) as infile:
		line_no = 1
		for line in infile:
			if "/download/" not in line:
				continue

			line_no += 1

			url_match = url_re.search(line)
			if url_match is None:
				continue

			url = url_match.group(0)
			author = unquote(url_match.group(1))
			name = url_match.group(2)

			parsed_url = urlparse(url)
			reason = parse_qs(parsed_url.query).get("reason")
			if reason:
				reason = reason[0]

			dt_match = dt_re.search(line)
			assert dt_match
			dt = datetime.datetime.strptime(dt_match.group(1), "%d/%b/%Y:%H:%M:%S %z")
			dt = datetime.datetime.utcfromtimestamp(dt.timestamp())
			date = dt.date()

			if date >= datetime.date(2022, 11, 6):
				continue

			# print(line)

			ua_match = ua_re.search(line)
			if ua_match is None:
				print("No UA: " + line)
				continue

			ua = ua_match.group(1)
			is_bot = ua_is_bot.get(ua)
			if is_bot:
				continue
			if is_bot is None:
				user_agent = user_agents.parse(ua)
				ua_is_bot[ua] = user_agent.is_bot
				if user_agent.is_bot:
					continue

			package_key = f"{author}/{name}".lower()
			package_id = package_id_by_key.get(package_key)
			if package_id is None:
				print(f"Package not found: {package_key}")
				continue

			key = f"{date.isoformat()}/{package_id}"
			# print(author, name, reason, ua, date, key)

			row = row_lookup.get(key)
			if not row:
				row = PackageDailyStats()
				row.date = date
				row.package_id = package_id

				row.platform_minetest = 0
				row.platform_other = 0
				row.reason_new = 0
				row.reason_dependency = 0
				row.reason_update = 0

				db.session.add(row)
				row_lookup[key] = row

			if ua.startswith("Minetest/") or ua.startswith("Luanti/"):
				row.platform_minetest += 1
			else:
				row.platform_other += 1

			if reason == "new":
				row.reason_new += 1
			elif reason == "dependency":
				row.reason_dependency += 1
			elif reason == "update":
				row.reason_update += 1

			# if line_no > 1000:
			# 	break

db.session.commit()
