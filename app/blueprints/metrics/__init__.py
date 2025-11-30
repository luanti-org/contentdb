# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime

from flask import Blueprint, make_response
from sqlalchemy import or_, and_
from sqlalchemy.sql.expression import func

from app.models import Package, db, User, UserRank, PackageState, PackageReview, ThreadReply, Collection, AuditLogEntry, \
	PackageTranslation, Language
from app.rediscache import get_key

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

	one_day_ago = datetime.datetime.now() - datetime.timedelta(days=1)
	one_week_ago = datetime.datetime.now() - datetime.timedelta(weeks=1)
	one_month_ago = datetime.datetime.now() - datetime.timedelta(weeks=4)

	active_users_day = User.query.filter(and_(User.rank != UserRank.BOT, or_(
		User.audit_log_entries.any(AuditLogEntry.created_at > one_day_ago),
		User.replies.any(ThreadReply.created_at > one_day_ago)))).count()
	active_users_week = User.query.filter(and_(User.rank != UserRank.BOT, or_(
		User.audit_log_entries.any(AuditLogEntry.created_at > one_week_ago),
		User.replies.any(ThreadReply.created_at > one_week_ago)))).count()
	active_users_month = User.query.filter(and_(User.rank != UserRank.BOT, or_(
		User.audit_log_entries.any(AuditLogEntry.created_at > one_month_ago),
		User.replies.any(ThreadReply.created_at > one_month_ago)))).count()

	reviews = PackageReview.query.count()
	comments = ThreadReply.query.count()
	collections = Collection.query.count()

	score_result = db.session.query(func.sum(Package.score)).one_or_none()
	score = 0 if not score_result or not score_result[0] else score_result[0]

	packages_with_translations = (db.session.query(PackageTranslation.package_id)
			.filter(PackageTranslation.language_id != "en")
			.group_by(PackageTranslation.package_id).count())
	packages_with_translations_meta = (db.session.query(PackageTranslation.package_id)
			.filter(PackageTranslation.short_desc.is_not(None), PackageTranslation.language_id != "en")
			.group_by(PackageTranslation.package_id).count())
	languages_packages = (db.session.query(PackageTranslation.language_id, func.count(Package.id))
			.select_from(PackageTranslation).outerjoin(Package)
			.order_by(db.asc(PackageTranslation.language_id))
			.group_by(PackageTranslation.language_id).all())
	languages_packages_meta = (db.session.query(PackageTranslation.language_id, func.count(Package.id))
			.select_from(PackageTranslation).outerjoin(Package)
			.filter(PackageTranslation.short_desc.is_not(None))
			.order_by(db.asc(PackageTranslation.language_id))
			.group_by(PackageTranslation.language_id).all())

	ret = ""
	ret += write_single_stat("contentdb_packages", "Total packages", "gauge", packages)
	ret += write_single_stat("contentdb_users", "Number of registered users", "gauge", users)
	ret += write_single_stat("contentdb_authors", "Number of users with packages", "gauge", authors)
	ret += write_single_stat("contentdb_users_active_1d", "Number of daily active registered users", "gauge", active_users_day)
	ret += write_single_stat("contentdb_users_active_1w", "Number of weekly active registered users", "gauge", active_users_week)
	ret += write_single_stat("contentdb_users_active_1m", "Number of monthly active registered users", "gauge", active_users_month)
	ret += write_single_stat("contentdb_downloads", "Total downloads", "gauge", downloads)
	ret += write_single_stat("contentdb_emails", "Number of emails sent", "counter", int(get_key("emails_sent", "0")))
	ret += write_single_stat("contentdb_reviews", "Number of reviews", "gauge", reviews)
	ret += write_single_stat("contentdb_comments", "Number of comments", "gauge", comments)
	ret += write_single_stat("contentdb_collections", "Number of collections", "gauge", collections)
	ret += write_single_stat("contentdb_score", "Total package score", "gauge", score)
	ret += write_single_stat("contentdb_packages_with_translations", "Number of packages with translations", "gauge",
			packages_with_translations)
	ret += write_single_stat("contentdb_packages_with_translations_meta", "Number of packages with translated meta",
			"gauge", packages_with_translations_meta)
	ret += write_array_stat("contentdb_languages_translated",
			"Number of packages per language", "gauge",
			[({"language": x[0]}, x[1]) for x in languages_packages])
	ret += write_array_stat("contentdb_languages_translated_meta",
			"Number of packages with translated short desc per language", "gauge",
			[({"language": x[0]}, x[1]) for x in languages_packages_meta])

	return ret


@bp.route("/metrics")
def metrics():
	response = make_response(generate_metrics(), 200)
	response.mimetype = "text/plain"
	return response
