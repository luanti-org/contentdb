# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
import random
import re
import sys
from time import sleep
from urllib.parse import urlparse, urljoin
from typing import Optional

import requests
import urllib3
from app import app
from sqlalchemy import or_, and_

from app.markdown import get_links, render_markdown
from app.models import db, Package, PackageState, PackageRelease, PackageScreenshot, AuditLogEntry
from app.tasks import celery, TaskError
from app.utils.models import post_bot_message, post_to_approval_thread, get_system_user


@celery.task()
def update_package_scores():
	Package.query.update({ "score_downloads": Package.score_downloads * 0.93 })
	db.session.commit()

	for package in Package.query.all():
		package.recalculate_score()

	db.session.commit()


def desc_contains(desc: str, search_str: str):
	if search_str.startswith("https://forum.luanti.org/viewtopic.php?%t="):
		reg = re.compile(search_str.replace(".", "\\.").replace("/", "\\/").replace("?", "\\?").replace("%", ".*"))
		return reg.search(desc)
	else:
		return search_str in desc


@celery.task()
def notify_about_git_forum_links():
	package_links = [(x[0], x[1]) for x in db.session.query(Package, Package.repo)
		.filter(Package.repo.is_not(None), Package.state == PackageState.APPROVED).all()]
	for pair in db.session.query(Package, Package.forums) \
			.filter(Package.forums.is_not(None), Package.state == PackageState.APPROVED).all():
		package_links.append((pair[0], f"https://forum.luanti.org/viewtopic.php?%t={pair[1]}"))

	clauses = [and_(Package.id != pair[0].id, Package.desc.ilike(f"%{pair[1]}%")) for pair in package_links]
	packages = Package.query.filter(Package.desc != "", Package.desc.is_not(None), Package.state == PackageState.APPROVED, or_(*clauses)).all()

	for package in packages:
		links = []

		for (link_package, link) in package_links:
			if link_package != package and desc_contains(package.desc.lower(), link.lower()):
				links.append((link_package, link))

		if len(links) > 0:
			title = "You should link to ContentDB pages instead of repos/forum topics"
			msg = "You should update your long description to link to ContentDB pages instead of repositories or " \
					"forum topics, where possible.  \n" \
					"You should also remove lists of dependencies, as CDB already shows that.\n\n" \
					"There's a ContentDB dialog redesign coming to Minetest 5.9.0. " \
					"Clicking a ContentDB link stays inside Minetest but an external repository / forums " \
					"link will open a web browser. Therefore, linking to ContentDB pages when referring to a " \
					"package will improve the user experience.\n\nHere are some URLs you might wish to replace:\n"

			for x in links:
				msg += f"\n* {x[1].replace('%', '')} -> {x[0].get_url('packages.view', absolute=True)}"

			post_bot_message(package, title, msg)

	db.session.commit()


@celery.task()
def clear_removed_packages(all_packages: bool):
	if all_packages:
		query = Package.query.filter_by(state=PackageState.DELETED)
	else:
		one_year_ago = datetime.datetime.now() - datetime.timedelta(days=365)
		query = Package.query.filter(
			Package.state == PackageState.DELETED,
			Package.downloads < 1000,
			~Package.audit_log_entries.any(AuditLogEntry.created_at > one_year_ago))

	count = query.count()
	for pkg in query.all():
		pkg.review_thread = None
		db.session.delete(pkg)
	db.session.commit()

	return f"Deleted {count} soft deleted packages packages"


def _url_exists(url: str) -> str:
	try:
		headers = {
			"User-Agent": "Mozilla/5.0 (compatible; ContentDB link checker; +https://content.luanti.org/)",
		}
		with requests.get(url, stream=True, headers=headers, timeout=10) as response:
			response.raise_for_status()
			return ""
	except requests.exceptions.HTTPError as e:
		if e.response.status_code == 403:
			return ""

		print(f"   - [{e.response.status_code}] <{url}>", file=sys.stderr)
		return str(e.response.status_code)
	except requests.exceptions.ConnectionError:
		return "ConnectionError"
	except urllib3.exceptions.ReadTimeoutError:
		return "timeout"


def _check_for_dead_links(package: Package) -> dict[str, str]:
	ignored_urls = set(app.config.get("LINK_CHECKER_IGNORED_URLS", ""))

	base_url = package.get_url("packages.view", absolute=True)
	links: set[Optional[str]] = {
		package.repo,
		package.website,
		package.issueTracker,
		package.forums_url,
		package.video_url,
		package.donate_url_actual,
		package.translation_url,
	}

	if package.desc:
		links.update(get_links(render_markdown(package.desc)))

	print(f"Checking {package.title} ({len(links)} links) for broken links", file=sys.stderr)

	bad_urls = {}

	for link in links:
		if link is None:
			continue

		abs_link = urljoin(base_url, link)
		url = urlparse(abs_link)
		if url.scheme != "http" and url.scheme != "https":
			continue

		if url.hostname in ignored_urls:
			continue

		res = _url_exists(abs_link)
		if res != "":
			bad_urls[link] = res

		# Prevent leaking information
		sleep(random.uniform(0.4, 0.6))

	return bad_urls


def _check_package(package: Package) -> Optional[str]:
	bad_urls = _check_for_dead_links(package)
	if len(bad_urls) > 0:
		return ("The following broken links were found on your package:\n\n" +
				"\n".join([f"- <{link}> [{res}]" for link, res in bad_urls.items()]))

	return None


@celery.task()
def check_package_on_submit(package_id: int):
	package = Package.query.get(package_id)
	if package is None:
		raise TaskError("No such package")

	if package.state != PackageState.READY_FOR_REVIEW:
		return

	msg = _check_package(package)
	if msg:
		system_user = get_system_user()
		post_to_approval_thread(package, system_user, msg, is_status_update=False, create_thread=True)
		db.session.commit()


@celery.task(rate_limit="5/m")
def check_package_for_broken_links(package_id: int):
	package = Package.query.get(package_id)
	if package is None:
		raise TaskError("No such package")

	msg = _check_package(package)
	if msg:
		post_bot_message(package, "Broken links", msg)
		db.session.commit()


@celery.task(bind=True)
def update_file_size_bytes(self):
	releases = PackageRelease.query.filter_by(file_size_bytes=0).all()
	screenshots = PackageScreenshot.query.filter_by(file_size_bytes=0).all()
	total = len(releases) + len(screenshots)
	self.update_state(state="PROGRESS", meta={
		"current": 0,
		"total": total,
	})

	for i, release in enumerate(releases):
		release.calculate_file_size_bytes()

		if i % 100 == 0:
			self.update_state(state="PROGRESS", meta={
				"current": i + 1,
				"total": total,
			})

	for i, ss in enumerate(screenshots):
		ss.calculate_file_size_bytes()

		if i % 100 == 0:
			self.update_state(state="PROGRESS", meta={
				"current": i + len(releases) + 1,
				"total": total,
			})

	db.session.commit()
