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

from typing import List, Tuple, Union, Optional

from flask_babel import lazy_gettext, LazyString
from sqlalchemy import and_, or_

from app.models import Package, PackageType, PackageState, PackageRelease, db, MetaPackage, ForumTopic, User, \
	Permission, UserRank


class PackageValidationNote:
	# level is danger, warning, or info
	level: str
	message: LazyString
	buttons: List[Tuple[str, LazyString]]

	# False to prevent "Approve"
	allow_approval: bool

	# False to prevent "Submit for Approval"
	allow_submit: bool

	def __init__(self, level: str, message: LazyString, allow_approval: bool, allow_submit: bool):
		self.level = level
		self.message = message
		self.buttons = []
		self.allow_approval = allow_approval
		self.allow_submit = allow_submit

	def add_button(self, url: str, label: LazyString) -> "PackageValidationNote":
		self.buttons.append((url, label))
		return self


def is_package_name_taken(normalised_name: str) -> bool:
	return Package.query.filter(
		and_(Package.state == PackageState.APPROVED,
			 or_(Package.name == normalised_name,
				 Package.name == normalised_name + "_game"))).count() > 0


def get_conflicting_mod_names(package: Package) -> set[str]:
	conflicting_modnames = (db.session.query(MetaPackage.name)
			.filter(MetaPackage.id.in_([mp.id for mp in package.provides]))
			.filter(MetaPackage.packages.any(and_(Package.id != package.id, Package.state == PackageState.APPROVED)))
			.all())
	conflicting_modnames += (db.session.query(ForumTopic.name)
			.filter(ForumTopic.name.in_([mp.name for mp in package.provides]))
			.filter(ForumTopic.topic_id != package.forums)
			.filter(~ db.exists().where(Package.forums == ForumTopic.topic_id))
			.order_by(db.asc(ForumTopic.name), db.asc(ForumTopic.title))
			.all())
	return set([x[0] for x in conflicting_modnames])


def count_packages_with_forum_topic(topic_id: int) -> int:
	return Package.query.filter(Package.forums == topic_id, Package.state != PackageState.DELETED).count() > 1


def get_forum_topic(topic_id: int) -> Optional[ForumTopic]:
	return ForumTopic.query.get(topic_id)


def validate_package_for_approval(package: Package) -> List[PackageValidationNote]:
	retval: List[PackageValidationNote] = []

	def template(level: str, allow_approval: bool, allow_submit: bool):
		def inner(msg: LazyString):
			note = PackageValidationNote(level, msg, allow_approval, allow_submit)
			retval.append(note)
			return note

		return inner

	danger = template("danger", allow_approval=False, allow_submit=False)
	warning = template("warning", allow_approval=True, allow_submit=True)
	info = template("info", allow_approval=False, allow_submit=True)

	if package.type != PackageType.MOD and is_package_name_taken(package.normalised_name):
		danger(lazy_gettext("A package already exists with this name. Please see Policy and Guidance 3"))

	if package.releases.filter(PackageRelease.task_id.is_(None)).count() == 0:
		if package.releases.count() == 0:
			message = lazy_gettext("You need to create a release before this package can be approved.")
		else:
			message = lazy_gettext("Release is still importing, or has an error.")

		danger(message) \
			.add_button(package.get_url("packages.create_release"), lazy_gettext("Create release")) \
			.add_button(package.get_url("packages.setup_releases"), lazy_gettext("Set up releases"))

		# Don't bother validating any more until we have a release
		return retval

	if (package.type == PackageType.GAME or package.type == PackageType.TXP) and \
			package.screenshots.count() == 0:
		danger(lazy_gettext("You need to add at least one screenshot."))

	missing_deps = package.get_missing_hard_dependencies_query().all()
	if len(missing_deps) > 0:
		missing_deps = ", ".join([ x.name for x in missing_deps])
		danger(lazy_gettext(
			"The following hard dependencies need to be added to ContentDB first: %(deps)s", deps=missing_deps))

	if package.type != PackageType.GAME and not package.supports_all_games and package.supported_games.count() == 0:
		danger(lazy_gettext(
			"What games does your package support? Please specify on the supported games page", deps=missing_deps)) \
			.add_button(package.get_url("packages.game_support"), lazy_gettext("Supported Games"))

	if "Other" in package.license.name or "Other" in package.media_license.name:
		info(lazy_gettext("Please wait for the license to be added to CDB."))

	# Check similar mod name
	conflicting_modnames = set()
	if package.type != PackageType.TXP:
		conflicting_modnames = get_conflicting_mod_names(package)

	if len(conflicting_modnames) > 4:
		warning(lazy_gettext("Please make sure that this package has the right to the names it uses."))
	elif len(conflicting_modnames) > 0:
		names_list = list(conflicting_modnames)
		names_list.sort()
		warning(lazy_gettext("Please make sure that this package has the right to the names %(names)s",
				names=", ".join(names_list))) \
			.add_button(package.get_url('packages.similar'), lazy_gettext("See more"))

	# Check forum topic
	if package.state != PackageState.APPROVED and package.forums is not None:
		if count_packages_with_forum_topic(package.forums) > 1:
			danger("<b>" + lazy_gettext("Error: Another package already uses this forum topic!") + "</b>")

		topic = get_forum_topic(package.forums)
		if topic is not None:
			if topic.author != package.author:
				danger("<b>" + lazy_gettext("Error: Forum topic author doesn't match package author.") + "</b>")
		elif package.type != PackageType.TXP:
			warning(lazy_gettext("Warning: Forum topic not found. The topic may have been created since the last forum crawl."))

	return retval


PACKAGE_STATE_FLOW = {
	PackageState.WIP: {PackageState.READY_FOR_REVIEW},
	PackageState.CHANGES_NEEDED: {PackageState.READY_FOR_REVIEW},
	PackageState.READY_FOR_REVIEW: {PackageState.WIP, PackageState.CHANGES_NEEDED, PackageState.APPROVED},
	PackageState.APPROVED: {PackageState.CHANGES_NEEDED},
	PackageState.DELETED: {PackageState.READY_FOR_REVIEW},
}


def can_move_to_state(package: Package, user: User, new_state: Union[str, PackageState]) -> bool:
	if not user.is_authenticated:
		return False

	if type(new_state) == str:
		new_state = PackageState[new_state]
	elif type(new_state) != PackageState:
		raise Exception("Unknown state given to can_move_to_state()")

	if new_state not in PACKAGE_STATE_FLOW[package.state]:
		return False

	if new_state == PackageState.READY_FOR_REVIEW or new_state == PackageState.APPROVED:
		# Can the user approve?
		if new_state == PackageState.APPROVED and not package.check_perm(user, Permission.APPROVE_NEW):
			return False

		# Must be able to edit or approve package to change its state
		if not (package.check_perm(user, Permission.APPROVE_NEW) or package.check_perm(user, Permission.EDIT_PACKAGE)):
			return False

		# Are there any validation warnings?
		validation_notes = validate_package_for_approval(package)
		for note in validation_notes:
			if not note.allow_submit or (new_state == PackageState.APPROVED and not note.allow_approval):
				return False

		return True

	elif new_state == PackageState.CHANGES_NEEDED:
		return package.check_perm(user, Permission.APPROVE_NEW)

	elif new_state == PackageState.WIP:
		return package.check_perm(user, Permission.EDIT_PACKAGE) and \
			(user in package.maintainers or user.rank.at_least(UserRank.ADMIN))

	return True
