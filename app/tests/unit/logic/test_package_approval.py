# ContentDB
# Copyright (C) rubenwardy
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

from unittest.mock import MagicMock, patch

from app.logic import package_approval
from app.models import Package, PackageType


class MockPackageHelper:
	package: Package

	def __init__(self, type_: PackageType = PackageType.MOD):
		self.package = MagicMock()

		self.package.type = type_
		self.package.name = "foobar"
		self.package.normalised_name.name = "foobar"
		self.package.author.username = "username"
		self.package.author.id = 3

		self.package.releases.filter.return_value.count.return_value = 0
		self.package.releases.count.return_value = 0
		self.package.get_url.return_value = "hi"
		self.package.screenshots.count.return_value = 0

	def add_release(self):
		self.package.releases.filter.return_value.count.return_value = 1
		self.package.releases.count.return_value = 1

	def add_pending_release(self):
		self.package.releases.filter.return_value.count.return_value = 0
		self.package.releases.count.return_value = 1

	def add_screenshot(self):
		self.package.screenshots.count.return_value = 1

	def add_missing_hard_deps(self):
		mod_name = MagicMock()
		mod_name.name = "missing"
		self.package.get_missing_hard_dependencies_query.return_value.all.return_value = [mod_name]

	def set_license(self, code_license: str, media_license: str):
		self.package.license.name = code_license
		self.package.media_license.name = media_license

	def set_no_game_support(self):
		assert self.package.type != PackageType.GAME
		self.package.supports_all_games = False
		self.package.supported_games.count.return_value = 0


def test_requires_release():
	mock_package = MockPackageHelper()

	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 1
	assert notes[0].message == "You need to create a release before this package can be approved."

	mock_package.add_pending_release()
	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 1
	assert notes[0].message == "Release is still importing, or has an error."


@patch("app.logic.package_approval.is_package_name_taken", MagicMock(return_value=False))
@patch("app.logic.package_approval.get_conflicting_mod_names", MagicMock(return_value=set()))
@patch("app.logic.package_approval.count_packages_with_forum_topic", MagicMock(return_value=1))
@patch("app.logic.package_approval.get_forum_topic")
def test_missing_hard_deps(get_forum_topic):
	mock_package = MockPackageHelper(PackageType.MOD)
	mock_package.add_release()
	mock_package.add_missing_hard_deps()
	mock_package.add_screenshot()

	topic = MagicMock()
	topic.author = mock_package.package.author
	get_forum_topic.return_value = topic

	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 1
	assert notes[0].message == "The following hard dependencies need to be added to ContentDB first: missing"


@patch("app.logic.package_approval.is_package_name_taken", MagicMock(return_value=True))
@patch("app.logic.package_approval.get_conflicting_mod_names", MagicMock(return_value={"one", "two"}))
@patch("app.logic.package_approval.count_packages_with_forum_topic", MagicMock(return_value=2))
@patch("app.logic.package_approval.get_forum_topic", MagicMock(return_value=None))
def test_requires_multiple_issues():
	mock_package = MockPackageHelper()
	mock_package.add_release()
	mock_package.set_license("Other", "Other")
	mock_package.set_no_game_support()
	mock_package.add_screenshot()

	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 5
	assert notes[0].message == "What games does your package support? Please specify on the supported games page"
	assert notes[1].message == "Please wait for the license to be added to CDB."
	assert notes[2].message == "Please make sure that this package has the right to the names one, two"
	assert notes[3].message == "<b>Error: Another package already uses this forum topic!</b>"
	assert notes[4].message == "Warning: Forum topic not found. The topic may have been created since the last forum crawl."


@patch("app.logic.package_approval.is_package_name_taken", MagicMock(return_value=False))
@patch("app.logic.package_approval.get_conflicting_mod_names", MagicMock(return_value=set()))
@patch("app.logic.package_approval.count_packages_with_forum_topic", MagicMock(return_value=1))
@patch("app.logic.package_approval.get_forum_topic")
def test_forum_topic_author_mismatch(get_forum_topic):
	mock_package = MockPackageHelper()
	mock_package.add_release()
	mock_package.add_screenshot()

	topic = MagicMock()
	get_forum_topic.return_value = topic

	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 1
	assert notes[0].message == "<b>Error: Forum topic author doesn't match package author.</b>"


@patch("app.logic.package_approval.is_package_name_taken", MagicMock(return_value=False))
@patch("app.logic.package_approval.get_conflicting_mod_names", MagicMock(return_value=set()))
@patch("app.logic.package_approval.count_packages_with_forum_topic", MagicMock(return_value=1))
@patch("app.logic.package_approval.get_forum_topic")
def test_passes(get_forum_topic):
	mock_package = MockPackageHelper()
	mock_package.add_release()
	mock_package.add_screenshot()

	topic = MagicMock()
	topic.author = mock_package.package.author
	get_forum_topic.return_value = topic

	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 0


@patch("app.logic.package_approval.is_package_name_taken", MagicMock(return_value=True))
@patch("app.logic.package_approval.get_conflicting_mod_names", MagicMock(return_value=set()))
@patch("app.logic.package_approval.count_packages_with_forum_topic", MagicMock(return_value=1))
@patch("app.logic.package_approval.get_forum_topic")
def test_games_txp_must_have_unique_name(get_forum_topic):
	mock_package = MockPackageHelper(PackageType.GAME)
	mock_package.add_release()
	mock_package.add_screenshot()

	topic = MagicMock()
	topic.author = mock_package.package.author
	get_forum_topic.return_value = topic

	notes = package_approval.validate_package_for_approval(mock_package.package)

	assert len(notes) == 1
	assert notes[0].message == "A package already exists with this name. Please see Policy and Guidance 3"


@patch("app.logic.package_approval.is_package_name_taken", MagicMock(return_value=False))
@patch("app.logic.package_approval.get_conflicting_mod_names", MagicMock(return_value=set()))
@patch("app.logic.package_approval.count_packages_with_forum_topic", MagicMock(return_value=1))
@patch("app.logic.package_approval.get_forum_topic")
def test_require_screenshots(get_forum_topic):
	mock_package = MockPackageHelper(PackageType.MOD)
	mock_package.add_release()

	topic = MagicMock()
	topic.author = mock_package.package.author
	get_forum_topic.return_value = topic

	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 1
	assert notes[0].message == "You need to add at least one screenshot."

	mock_package.add_screenshot()
	notes = package_approval.validate_package_for_approval(mock_package.package)
	assert len(notes) == 0
