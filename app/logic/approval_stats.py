# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
from collections import namedtuple, defaultdict
from typing import Dict, Optional
from sqlalchemy import or_

from app.models import AuditLogEntry, db, PackageState


class PackageInfo:
	state: Optional[PackageState]
	first_submitted: Optional[datetime.datetime]
	last_change: Optional[datetime.datetime]
	approved_at: Optional[datetime.datetime]
	wait_time: int
	total_approval_time: int
	is_in_range: bool
	events: list[tuple[str, str, str]]

	def __init__(self):
		self.state = None
		self.first_submitted = None
		self.last_change = None
		self.approved_at = None
		self.wait_time = 0
		self.total_approval_time = -1
		self.is_in_range = False
		self.events = []

	def __lt__(self, other):
		return self.wait_time < other.wait_time

	def __dict__(self):
		return {
			"first_submitted": self.first_submitted.isoformat(),
			"last_change": self.last_change.isoformat(),
			"approved_at": self.approved_at.isoformat() if self.approved_at else None,
			"wait_time": self.wait_time,
			"total_approval_time": self.total_approval_time if self.total_approval_time >= 0 else None,
			"events": [ { "date": x[0], "by": x[1], "title": x[2] } for x in self.events ],
		}

	def add_event(self, created_at: datetime.datetime, causer: str, title: str):
		self.events.append((created_at.isoformat(), causer, title))


def get_state(title: str):
	if title.startswith("Approved "):
		return PackageState.APPROVED

	assert title.startswith("Marked ")

	for state in PackageState:
		if state.value in title:
			return state

	if "Work in Progress" in title:
		return PackageState.WIP

	raise Exception(f"Unable to get state for title {title}")


Result = namedtuple("Result", "editor_approvals packages_info avg_turnaround_time max_turnaround_time")


def _get_approval_statistics(entries: list[AuditLogEntry], start_date: Optional[datetime.datetime] = None, end_date: Optional[datetime.datetime] = None) -> Result:
	editor_approvals = defaultdict(int)
	package_info: Dict[str, PackageInfo] = {}
	ignored_packages = set()
	turnaround_times: list[int] = []

	for entry in entries:
		package_id = str(entry.package.get_id())
		if package_id in ignored_packages:
			continue

		info = package_info.get(package_id, PackageInfo())
		package_info[package_id] = info

		is_in_range = (((start_date is None or entry.created_at >= start_date) and
				(end_date is None or entry.created_at <= end_date)))
		info.is_in_range = info.is_in_range or is_in_range

		new_state = get_state(entry.title.replace("…", "") + (entry.description or ""))
		if new_state == info.state:
			continue

		info.add_event(entry.created_at, entry.causer.username if entry.causer else None, new_state.value)

		if info.state == PackageState.READY_FOR_REVIEW:
			seconds = int((entry.created_at - info.last_change).total_seconds())
			info.wait_time += seconds
			if is_in_range:
				turnaround_times.append(seconds)

		if new_state == PackageState.APPROVED:
			ignored_packages.add(package_id)
			info.approved_at = entry.created_at
			if is_in_range:
				editor_approvals[entry.causer.username] += 1
			if info.first_submitted is not None:
				info.total_approval_time = int((entry.created_at - info.first_submitted).total_seconds())
		elif new_state == PackageState.READY_FOR_REVIEW:
			if info.first_submitted is None:
				info.first_submitted = entry.created_at

		info.state = new_state
		info.last_change = entry.created_at

	packages_info_2 = {}
	package_count = 0
	for package_id, info in package_info.items():
		if info.first_submitted and info.is_in_range:
			package_count += 1
			packages_info_2[package_id] = info

	if len(turnaround_times) > 0:
		avg_turnaround_time = sum(turnaround_times) / len(turnaround_times)
		max_turnaround_time = max(turnaround_times)
	else:
		avg_turnaround_time = 0
		max_turnaround_time = 0

	return Result(editor_approvals, packages_info_2, avg_turnaround_time, max_turnaround_time)


def get_approval_statistics(start_date: Optional[datetime.datetime] = None, end_date: Optional[datetime.datetime] = None) -> Result:
	entries = AuditLogEntry.query.filter(AuditLogEntry.package).filter(or_(
		AuditLogEntry.title.like("Approved %"),
		AuditLogEntry.title.like("Marked %"))
	).order_by(db.asc(AuditLogEntry.created_at)).all()

	return _get_approval_statistics(entries, start_date, end_date)
