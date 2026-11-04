# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

from flask import Blueprint, make_response
from sqlalchemy import or_, and_
from sqlalchemy.sql.expression import func

from app.models import Package, db, User, UserRank, PackageState, PackageReview, ThreadReply, Collection, AuditLogEntry, \
	PackageTranslation, Language
from app.rediscache import get_key, get_download_events

bp = Blueprint("metrics", __name__)


def generate_metrics():
	def write_single_stat(name, help, type, value):
		fmt = "# HELP {name} {help}\n# TYPE {name} {type}\n{name} {value}\n\n"

		return fmt.format(name=name, help=help, type=type, value=value)

	def gen_labels(labels):
		pieces = [f"{key}=\"{val}\"" for key, val in labels.items()]
		return ",".join(pieces)

	def write_array_stat(name, help, type, data):
		result = "# HELP {name} {help}\n# TYPE {name} {type}\n" \
			.format(name=name, help=help, type=type)

		for entry in data:
			assert(len(entry) == 2)
			result += "{name}{{{labels}}} {value}\n" \
				.format(name=name, labels=gen_labels(entry[0]), value=entry[1])

		return result + "\n"

	downloads_result = db.session.query(func.sum(Package.downloads)).one_or_none()
	downloads = 0 if not downloads_result or not downloads_result[0] else downloads_result[0]

	packages = Package.query.filter_by(state=PackageState.APPROVED).count()
	users = User.query.filter(User.rank > UserRank.NOT_JOINED, User.rank != UserRank.BOT, User.is_active).count()
	authors = User.query.filter(User.packages.any(state=PackageState.APPROVED)).count()

	now = datetime.datetime.utcnow()
	one_day_ago = now - datetime.timedelta(days=1)
	one_week_ago = now - datetime.timedelta(weeks=1)
	one_month_ago = now - datetime.timedelta(days=30)

	active_users_day = User.query.filter(and_(User.rank != UserRank.BOT, or_(
		User.audit_log_entries.any(AuditLogEntry.created_at > one_day_ago),
		User.replies.any(ThreadReply.created_at > one_day_ago)))).count()
	active_users_week = User.query.filter(and_(User.rank != UserRank.BOT, or_(
		User.audit_log_entries.any(AuditLogEntry.created_at > one_week_ago),
		User.replies.any(ThreadReply.created_at > one_week_ago)))).count()
	active_users_month = User.query.filter(and_(User.rank != UserRank.BOT, or_(
		User.audit_log_entries.any(AuditLogEntry.created_at > one_month_ago),
		User.replies.any(ThreadReply.created_at > one_month_ago)))).count()

	reviews = PackageReview.query.filter_by(approved=True).count()
	comments = ThreadReply.query.count()
	collections = Collection.query.count()

	score_result = db.session.query(func.sum(Package.score)).filter(Package.state == PackageState.APPROVED).one_or_none()
	score = 0 if not score_result or not score_result[0] else score_result[0]

	translations_filter = and_(Package.state == PackageState.APPROVED, PackageTranslation.language_id != "en")
	translations_meta_filter = and_(translations_filter, PackageTranslation.short_desc.is_not(None))

	packages_with_translations = (db.session.query(func.count(func.distinct(PackageTranslation.package_id)))
			.select_from(PackageTranslation).join(Package)
			.filter(translations_filter).scalar())
	packages_with_translations_meta = (db.session.query(func.count(func.distinct(PackageTranslation.package_id)))
			.select_from(PackageTranslation).join(Package)
			.filter(translations_meta_filter).scalar())
	languages_packages = (db.session.query(PackageTranslation.language_id, func.count(func.distinct(Package.id)))
			.select_from(PackageTranslation).join(Package)
			.filter(translations_filter)
			.order_by(db.asc(PackageTranslation.language_id))
			.group_by(PackageTranslation.language_id).all())
	languages_packages_meta = (db.session.query(PackageTranslation.language_id, func.count(func.distinct(Package.id)))
			.select_from(PackageTranslation).join(Package)
			.filter(translations_meta_filter)
			.order_by(db.asc(PackageTranslation.language_id))
			.group_by(PackageTranslation.language_id).all())

	ret = ""
	ret += write_single_stat("contentdb_packages", "Number of approved packages", "gauge", packages)
	ret += write_single_stat("contentdb_users", "Number of registered users", "gauge", users)
	ret += write_single_stat("contentdb_authors", "Number of users with packages", "gauge", authors)
	ret += write_single_stat("contentdb_users_active_1d", "Number of daily active registered users", "gauge", active_users_day)
	ret += write_single_stat("contentdb_users_active_1w", "Number of weekly active registered users", "gauge", active_users_week)
	ret += write_single_stat("contentdb_users_active_1m", "Number of registered users active in the last 30 days", "gauge", active_users_month)
	ret += write_single_stat("contentdb_downloads", "Total downloads, deduplicated by IP", "gauge", downloads)
	ret += write_array_stat("contentdb_download_events_total",
			"Number of download events. Resets when Redis does, use rate() or increase()", "counter",
			[({"reason": reason, "platform": platform}, count) for reason, platform, count in get_download_events()])
	ret += write_single_stat("contentdb_emails_total", "Number of emails sent", "counter", int(get_key("emails_sent", "0")))
	ret += write_single_stat("contentdb_reviews", "Number of reviews", "gauge", reviews)
	ret += write_single_stat("contentdb_comments", "Number of comments", "gauge", comments)
	ret += write_single_stat("contentdb_collections", "Number of collections", "gauge", collections)
	ret += write_single_stat("contentdb_score", "Total score of approved packages", "gauge", score)
	ret += write_single_stat("contentdb_packages_with_translations", "Number of packages with translations", "gauge",
			packages_with_translations)
	ret += write_single_stat("contentdb_packages_with_translations_meta", "Number of packages with translated meta",
			"gauge", packages_with_translations_meta)
	ret += write_array_stat("contentdb_languages_translated",
			"Number of approved packages with translations per language", "gauge",
			[({"language": x[0]}, x[1]) for x in languages_packages])
	ret += write_array_stat("contentdb_languages_translated_meta",
			"Number of approved packages with translated short desc per language", "gauge",
			[({"language": x[0]}, x[1]) for x in languages_packages_meta])

	return ret


@bp.route("/metrics")
def metrics():
	response = make_response(generate_metrics(), 200)
	response.mimetype = "text/plain"
	return response
