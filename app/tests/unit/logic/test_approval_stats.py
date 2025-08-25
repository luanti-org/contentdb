# ContentDB
# Copyright (C) 2024  rubenwardy
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

import datetime
from app.logic.approval_stats import _get_approval_statistics
from app.models import AuditLogEntry, User


class MockPackage:
	def __init__(self, id_: str):
		self.id_ = id_

	def get_id(self):
		return self.id_


class MockEntry:
	def __init__(self, date: str, package_id: str, username: str, title: str):
		causer = User()
		causer.username = username

		self.causer = causer
		self.created_at = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S%z")
		self.title = title
		self.description = None
		self.package = MockPackage(package_id)


# noinspection PyTypeChecker
def make_entry(date: str, package_id: str, username: str, title: str) -> AuditLogEntry:
	return MockEntry(date, package_id, username, title)


def test_empty():
	stats = _get_approval_statistics([])
	assert not stats.editor_approvals
	assert not stats.packages_info
	assert stats.avg_turnaround_time == 0


def test_package_simple():
	package_1 = "user1/one"
	stats = _get_approval_statistics([
		make_entry("2023-04-03T12:32:00Z", package_1, "user1", "Marked Title as Ready for Review"),
		make_entry("2023-04-06T12:32:00Z", package_1, "reviewer", "Marked Title as Changes Needed"),
		make_entry("2023-04-07T12:32:00Z", package_1, "user1", "Marked Title as Ready for Review"),
		make_entry("2023-04-08T12:32:00Z", package_1, "reviewer", "Approved Title"),
	])

	assert stats.packages_info[package_1].total_approval_time == 5*60*60*24
	assert stats.packages_info[package_1].wait_time == 4*60*60*24


def test_average_turnaround():
	package_1 = "user1/one"
	package_2 = "user2/two"
	stats = _get_approval_statistics([
		make_entry("2023-04-03T12:00:00Z", package_1, "user1", "Marked Title as Ready for Review"),
		make_entry("2023-04-03T18:00:00Z", package_2, "user2", "Marked Title as Ready for Review"),
		make_entry("2023-04-06T12:00:00Z", package_1, "reviewer", "Marked Title as Changes Needed"),
		make_entry("2023-04-07T12:00:00Z", package_1, "user1", "Marked Title as Ready for Review"),
		make_entry("2023-04-08T12:00:00Z", package_1, "reviewer", "Approved Title"),
		make_entry("2023-04-10T18:00:00Z", package_2, "reviewer", "Approved Title"),
	])

	assert stats.avg_turnaround_time == 316800


def test_editor_counts():
	package_1 = "user1/one"
	package_2 = "user1/two"
	package_3 = "user1/three"
	stats = _get_approval_statistics([
		make_entry("2023-04-03T12:00:00Z", package_1, "user1", "Marked Title as Ready for Review"),
		make_entry("2023-04-03T12:00:00Z", package_2, "user1", "Marked Title as Ready for Review"),
		make_entry("2023-04-03T12:00:00Z", package_3, "user1", "Marked Title as Ready for Review"),
		make_entry("2023-04-08T12:00:00Z", package_1, "reviewer", "Approved Title"),
		make_entry("2023-04-10T18:00:00Z", package_2, "reviewer", "Approved Title"),
		make_entry("2023-04-11T18:00:00Z", package_3, "reviewer2", "Approved Title"),
	])

	assert len(stats.editor_approvals) == 2
	assert stats.editor_approvals["reviewer"] == 2
	assert stats.editor_approvals["reviewer2"] == 1
