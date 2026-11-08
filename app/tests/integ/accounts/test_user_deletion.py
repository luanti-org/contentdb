# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import datetime
from dataclasses import dataclass

from app.domain.user_deletion import delete_user
from app.tasks.pkgtasks import clear_removed_packages
from app.models import db, User, UserRank, Package, PackageState, PackageType, PackageRelease, ReleaseState, PackageScreenshot, \
	Thread, ThreadReply, PackageReview, PackageReviewVote, Collection, CollectionPackage, APIToken, AuditLogEntry, \
	AuditSeverity, Report, ReportCategory, Notification, NotificationType, MetaPackage, Dependency, Tag, \
	PackageAlias, PackageUpdateConfig, PackageDailyStats, PackageGameSupport, PackageTranslation, Language, UserBan, \
	ForumTopic, OAuthClient, UserSession, UserEmailVerification, UserNotificationPreferences
from app.utils.misc import hash_token, random_string
from ..utils import make_package


def make_user(username: str) -> User:
	user = User(username, active=True)
	user.rank = UserRank.MEMBER
	db.session.add(user)
	return user


def make_thread(author: User, package: Package | None, title: str = "Hello") -> Thread:
	thread = Thread()
	thread.title = title
	thread.author = author
	thread.package = package
	db.session.add(thread)
	add_reply(thread, author)
	return thread


def add_reply(thread: Thread, author: User) -> ThreadReply:
	reply = ThreadReply()
	reply.thread = thread
	reply.author = author
	reply.comment = f"Comment by {author.username}"
	db.session.add(reply)
	return reply


def make_review(author: User, package: Package) -> PackageReview:
	review = PackageReview()
	review.package = package
	review.author = author
	review.rating = 5
	db.session.add(review)

	thread = make_thread(author, package, f"Review by {author.username}")
	thread.review = review
	return review


def add_vote(review: PackageReview, user: User):
	vote = PackageReviewVote()
	vote.review = review
	vote.user = user
	vote.is_positive = True
	db.session.add(vote)
	review.update_score()


def make_token(owner: User, package: Package | None = None) -> APIToken:
	token = APIToken()
	token.name = "test"
	token.owner = owner
	token.package = package
	token.access_token_hash = hash_token(random_string(32))
	db.session.add(token)
	return token


def make_collection(author: User, packages: list[Package]) -> Collection:
	collection = Collection()
	collection.author = author
	collection.name = "favorites"
	collection.title = "Favorites"
	collection.short_description = "Favorites"
	db.session.add(collection)
	for package in packages:
		item = CollectionPackage()
		item.package = package
		item.collection = collection
		db.session.add(item)
	return collection


def make_report(user: User | None, thread: Thread | None) -> Report:
	report = Report()
	report.id = random_string(24)
	report.user = user
	report.thread = thread
	report.category = ReportCategory.SPAM
	report.title = "Spam"
	report.message = "Spam"
	db.session.add(report)
	return report


def get_meta(name: str) -> MetaPackage:
	meta = MetaPackage.query.filter_by(name=name).first()
	if meta is None:
		meta = MetaPackage(name)
		db.session.add(meta)
		db.session.flush()
	return meta


def add_package_content(package: Package):
	release = PackageRelease()
	release.package = package
	release.name = "1.0"
	release.title = "1.0"
	release.upload_path = "/uploads/release.zip"
	release.state = ReleaseState.APPROVED
	db.session.add(release)

	screenshot = PackageScreenshot()
	screenshot.package = package
	screenshot.title = "Screenshot"
	screenshot.upload_path = "/uploads/abc.png"
	screenshot.approved = True
	screenshot.width = 1920
	screenshot.height = 1080
	db.session.add(screenshot)
	package.cover_image = screenshot

	package.review_thread = make_thread(package.author, package, "Approval thread")
	package.tags.append(Tag.query.first())

	package.provides.append(get_meta(package.name))
	db.session.add(Dependency(package, meta=get_meta("default"), optional=False))

	alias = PackageAlias("old_author", package.name)
	alias.package = package
	db.session.add(alias)

	update_config = PackageUpdateConfig()
	update_config.package = package
	db.session.add(update_config)

	stats = PackageDailyStats()
	stats.package = package
	stats.date = datetime.date.today()
	db.session.add(stats)

	translation = PackageTranslation()
	translation.package = package
	translation.language = Language.query.get("de")
	translation.title = "Titel"
	db.session.add(translation)


@dataclass
class Scenario:
	victim_id: int
	victim_package_ids: list[int]
	other_id: int
	other_package_id: int
	other_collection_id: int
	other_thread_id: int
	other_review_id: int
	victim_reply_id: int
	victim_report_id: int
	other_report_id: int
	victim_audit_id: int
	package_audit_id: int


def make_scenario() -> Scenario:
	language = Language()
	language.id = "de"
	language.title = "German"
	db.session.add(language)

	victim = make_user("victim")
	other = make_user("other")

	victim_mod = make_package("victim_mod", victim)
	victim_mod.maintainers.extend([victim, other])
	victim_game = make_package("victim_game", victim)
	victim_game.type = PackageType.GAME
	victim_game.maintainers.append(victim)
	other_mod = make_package("other_mod", other)
	other_mod.maintainers.extend([other, victim])
	db.session.flush()

	add_package_content(victim_mod)
	add_package_content(victim_game)
	add_package_content(other_mod)

	# Links from the other user's content to the victim's packages
	db.session.add(Dependency(other_mod, package=victim_mod))
	game_support = PackageGameSupport()
	game_support.package = other_mod
	game_support.game = victim_game
	db.session.add(game_support)
	other_collection = make_collection(other, [victim_mod, other_mod])
	make_token(other, victim_mod)

	# The other user's content on the victim's packages, which goes with the packages
	make_thread(other, victim_mod)
	make_review(other, victim_mod)

	# The victim's content on the other user's package
	victim_review = make_review(victim, other_mod)
	add_vote(victim_review, other)
	other_review = make_review(other, other_mod)
	add_vote(other_review, victim)
	other_thread = make_thread(other, other_mod)
	victim_reply = add_reply(other_thread, victim)
	other_thread.watchers.extend([victim, other])
	make_collection(victim, [other_mod])
	make_token(victim, other_mod)

	# Moderation and logs
	victim_report = make_report(victim, make_thread(victim, None, "Report"))
	other_report = make_report(other, make_thread(other, None, "Report about victim"))
	add_reply(other_report.thread, victim)
	add_reply(victim_report.thread, other)
	victim_audit = AuditLogEntry(victim, AuditSeverity.NORMAL, "Edited other_mod", None, other_mod)
	package_audit = AuditLogEntry(other, AuditSeverity.NORMAL, "Edited victim_mod", None, victim_mod)
	db.session.add(victim_audit)
	db.session.add(package_audit)

	# Notifications
	db.session.add(Notification(other, victim, NotificationType.OTHER, "From victim", "/"))
	db.session.add(Notification(victim, other, NotificationType.OTHER, "To victim", "/"))
	db.session.add(Notification(other, other, NotificationType.OTHER, "About victim_mod", "/", victim_mod))

	db.session.commit()

	return Scenario(
		victim_id=victim.id,
		victim_package_ids=[victim_mod.id, victim_game.id],
		other_id=other.id,
		other_package_id=other_mod.id,
		other_collection_id=other_collection.id,
		other_thread_id=other_thread.id,
		other_review_id=other_review.id,
		victim_reply_id=victim_reply.id,
		victim_report_id=victim_report.id,
		other_report_id=other_report.id,
		victim_audit_id=victim_audit.id,
		package_audit_id=package_audit.id,
	)


def test_delete_user_removes_user_and_packages(client):
	scenario = make_scenario()

	delete_user(User.query.filter_by(id=scenario.victim_id).one())
	db.session.commit()
	db.session.expire_all()

	assert User.query.get(scenario.victim_id) is None
	for package_id in scenario.victim_package_ids:
		assert Package.query.get(package_id) is None

	# No rows are left pointing at the deleted user or packages
	victim_package_ids = scenario.victim_package_ids
	assert Thread.query.filter(Thread.package_id.in_(victim_package_ids)).count() == 0
	assert Thread.query.filter_by(author_id=scenario.victim_id).count() == 0
	assert ThreadReply.query.filter_by(author_id=scenario.victim_id).count() == 0
	assert PackageReview.query.filter(PackageReview.package_id.in_(victim_package_ids)).count() == 0
	assert PackageReview.query.filter_by(author_id=scenario.victim_id).count() == 0
	assert PackageReviewVote.query.filter_by(user_id=scenario.victim_id).count() == 0
	assert PackageRelease.query.filter(PackageRelease.package_id.in_(victim_package_ids)).count() == 0
	assert PackageScreenshot.query.filter(PackageScreenshot.package_id.in_(victim_package_ids)).count() == 0
	assert Dependency.query.filter(Dependency.depender_id.in_(victim_package_ids)).count() == 0
	assert Dependency.query.filter(Dependency.package_id.in_(victim_package_ids)).count() == 0
	assert Dependency.query.filter(Dependency.depender_id.is_(None)).count() == 0
	assert PackageGameSupport.query.filter(PackageGameSupport.game_id.in_(victim_package_ids)).count() == 0
	assert CollectionPackage.query.filter(CollectionPackage.package_id.in_(victim_package_ids)).count() == 0
	assert Collection.query.filter_by(author_id=scenario.victim_id).count() == 0
	assert APIToken.query.filter_by(owner_id=scenario.victim_id).count() == 0
	assert APIToken.query.filter(APIToken.package_id.in_(victim_package_ids)).count() == 0
	assert PackageAlias.query.filter(PackageAlias.package_id.in_(victim_package_ids)).count() == 0
	assert PackageTranslation.query.filter(PackageTranslation.package_id.in_(victim_package_ids)).count() == 0
	assert PackageDailyStats.query.filter(PackageDailyStats.package_id.in_(victim_package_ids)).count() == 0
	assert PackageUpdateConfig.query.filter(PackageUpdateConfig.package_id.in_(victim_package_ids)).count() == 0
	assert Notification.query.filter_by(user_id=scenario.victim_id).count() == 0
	assert Notification.query.filter_by(causer_id=scenario.victim_id).count() == 0
	assert Notification.query.filter(Notification.package_id.in_(victim_package_ids)).count() == 0


def test_delete_user_keeps_other_users_content(client):
	scenario = make_scenario()

	delete_user(User.query.filter_by(id=scenario.victim_id).one())
	db.session.commit()
	db.session.expire_all()

	other = User.query.get(scenario.other_id)
	assert other is not None

	other_mod = Package.query.get(scenario.other_package_id)
	assert other_mod is not None
	assert other_mod.maintainers == [other]
	assert other_mod.dependencies.count() == 1
	assert other_mod.supported_games.count() == 0
	assert other_mod.releases.count() == 1
	assert other_mod.screenshots.count() == 1
	assert other_mod.cover_image is not None
	assert other_mod.review_thread is not None
	assert other_mod.tokens == []

	collection = Collection.query.get(scenario.other_collection_id)
	assert collection is not None
	assert [x.package for x in collection.items] == [other_mod]

	thread = Thread.query.get(scenario.other_thread_id)
	assert thread is not None
	assert thread.watchers == [other]
	assert [x.author for x in thread.replies] == [other]
	assert ThreadReply.query.get(scenario.victim_reply_id) is None

	review = PackageReview.query.get(scenario.other_review_id)
	assert review is not None
	assert review.votes == []
	assert review.score == 1
	assert [x.author for x in other_mod.reviews] == [other]

	assert Notification.query.filter_by(user_id=scenario.other_id, title="From victim").count() == 0
	assert APIToken.query.filter_by(owner_id=scenario.other_id).count() == 0


def test_delete_user_keeps_reports_and_audit_log(client):
	scenario = make_scenario()

	delete_user(User.query.filter_by(id=scenario.victim_id).one())
	db.session.commit()
	db.session.expire_all()

	system_user = User.query.filter_by(username="ContentDB").one()

	# Report threads and the victim's comments in them are kept, reassigned to the system user
	victim_report = Report.query.get(scenario.victim_report_id)
	assert victim_report is not None
	assert victim_report.user is None
	assert victim_report.thread is not None
	assert victim_report.thread.author == system_user
	assert [x.author.username for x in victim_report.thread.replies] == ["ContentDB", "other"]
	assert [x.comment for x in victim_report.thread.replies] == ["Comment by victim", "Comment by other"]

	other_report = Report.query.get(scenario.other_report_id)
	assert other_report is not None
	assert other_report.user_id == scenario.other_id
	assert other_report.thread is not None
	assert other_report.thread.author_id == scenario.other_id
	assert [x.author.username for x in other_report.thread.replies] == ["other", "ContentDB"]
	assert [x.comment for x in other_report.thread.replies] == ["Comment by other", "Comment by victim"]

	victim_audit = AuditLogEntry.query.get(scenario.victim_audit_id)
	assert victim_audit is not None
	assert victim_audit.causer is None
	assert victim_audit.package_id == scenario.other_package_id

	package_audit = AuditLogEntry.query.get(scenario.package_audit_id)
	assert package_audit is not None
	assert package_audit.causer_id == scenario.other_id
	assert package_audit.package is None


def add_account_rows(user: User):
	user_ban = UserBan()
	user_ban.banned_by = User.query.filter_by(username="rubenwardy").one()
	user_ban.message = "test"
	user.ban = user_ban
	user.rank = UserRank.BANNED

	topic = ForumTopic()
	topic.topic_id = 1234
	topic.author = user
	topic.type = PackageType.MOD
	topic.title = "My mod"
	topic.posts = 1
	topic.views = 1
	db.session.add(topic)

	oauth_client = OAuthClient()
	oauth_client.id = random_string(24)
	oauth_client.title = "My app"
	oauth_client.secret_hash = hash_token(random_string(32))
	oauth_client.redirect_url = "https://example.com"
	oauth_client.owner = user
	db.session.add(oauth_client)
	app_token = make_token(User.query.filter_by(username="rubenwardy").one())
	app_token.client = oauth_client

	user_session = UserSession()
	user_session.user = user
	user_session.token_hash = hash_token(random_string(32))
	db.session.add(user_session)

	verification = UserEmailVerification()
	verification.user = user
	verification.email = "victim@example.com"
	db.session.add(verification)

	db.session.add(UserNotificationPreferences(user))


def test_delete_user_with_account_rows(client):
	victim = make_user("victim")
	add_account_rows(victim)
	db.session.commit()
	victim_id = victim.id

	delete_user(victim)
	db.session.commit()
	db.session.expire_all()

	assert User.query.get(victim_id) is None
	assert UserBan.query.filter_by(user_id=victim_id).count() == 0
	assert ForumTopic.query.filter_by(author_id=victim_id).count() == 0
	assert OAuthClient.query.filter_by(owner_id=victim_id).count() == 0
	assert APIToken.query.filter(APIToken.client_id.isnot(None)).count() == 0
	assert UserSession.query.filter_by(user_id=victim_id).count() == 0
	assert UserEmailVerification.query.filter_by(user_id=victim_id).count() == 0
	assert UserNotificationPreferences.query.filter_by(user_id=victim_id).count() == 0


def test_delete_user_keeps_bans_they_issued(client):
	victim = make_user("victim")
	banned = make_user("banned")
	user_ban = UserBan()
	user_ban.banned_by = victim
	user_ban.message = "test"
	banned.ban = user_ban
	db.session.commit()
	victim_id = victim.id

	delete_user(victim)
	db.session.commit()
	db.session.expire_all()

	assert User.query.get(victim_id) is None
	assert User.query.filter_by(username="banned").one().ban.banned_by.username == "ContentDB"


def test_hard_delete_package_keeps_other_packages(client):
	scenario = make_scenario()
	for package_id in scenario.victim_package_ids:
		Package.query.filter_by(id=package_id).one().state = PackageState.DELETED
	db.session.commit()

	clear_removed_packages(True)
	db.session.expire_all()

	for package_id in scenario.victim_package_ids:
		assert Package.query.get(package_id) is None

	assert User.query.get(scenario.victim_id) is not None
	other_mod = Package.query.filter_by(id=scenario.other_package_id).one()
	assert other_mod.dependencies.count() == 1
	assert other_mod.supported_games.count() == 0
	assert [x.package for x in Collection.query.filter_by(id=scenario.other_collection_id).one().items] == [other_mod]
	assert AuditLogEntry.query.filter_by(id=scenario.package_audit_id).one().package is None
