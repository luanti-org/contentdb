# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import datetime
from datetime import timedelta
from typing import Optional

from app.models import User, Package, PackageDailyStats, db, PackageState
from sqlalchemy import func


def daterange(start_date, end_date):
	for n in range(int((end_date - start_date).days) + 1):
		yield start_date + timedelta(n)


keys = ["platform_minetest", "platform_other", "reason_new",
		"reason_dependency", "reason_update"]


def flatten_data(stats):
	start_date = stats[0].date
	end_date = stats[-1].date
	result = {
		"start": start_date.isoformat(),
		"end": end_date.isoformat(),
	}

	for key in keys:
		result[key] = []

	i = 0
	for date in daterange(start_date, end_date):
		stat = stats[i]
		if stat.date == date:
			for key in keys:
				result[key].append(getattr(stat, key))

			i += 1
		else:
			for key in keys:
				result[key].append(0)

	return result


def get_package_stats(package: Package, start_date: Optional[datetime.date], end_date: Optional[datetime.date]):
	query = package.daily_stats.order_by(db.asc(PackageDailyStats.date))
	if start_date:
		query = query.filter(PackageDailyStats.date >= start_date)
	if end_date:
		query = query.filter(PackageDailyStats.date <= end_date)

	stats = query.all()
	if len(stats) == 0:
		return None

	return flatten_data(stats)


def get_package_stats_for_user(user: User, start_date: Optional[datetime.date], end_date: Optional[datetime.date]):
	query = db.session \
		.query(PackageDailyStats.date,
			func.sum(PackageDailyStats.platform_minetest).label("platform_minetest"),
			func.sum(PackageDailyStats.platform_other).label("platform_other"),
			func.sum(PackageDailyStats.reason_new).label("reason_new"),
			func.sum(PackageDailyStats.reason_dependency).label("reason_dependency"),
			func.sum(PackageDailyStats.reason_update).label("reason_update")) \
		.filter(PackageDailyStats.package.has(author_id=user.id))

	if start_date:
		query = query.filter(PackageDailyStats.date >= start_date)
	if end_date:
		query = query.filter(PackageDailyStats.date <= end_date)

	stats = query.order_by(db.asc(PackageDailyStats.date)) \
		.group_by(PackageDailyStats.date) \
		.all()
	if len(stats) == 0:
		return None

	results = flatten_data(stats)
	results["package_downloads"] = get_package_overview_for_user(user, stats[0].date, stats[-1].date)

	return results


def get_package_overview_for_user(user: Optional[User], start_date: datetime.date, end_date: datetime.date):
	query = db.session \
		.query(PackageDailyStats.package_id, PackageDailyStats.date,
			(PackageDailyStats.platform_minetest + PackageDailyStats.platform_other).label("downloads"))

	if user:
		query = query.filter(PackageDailyStats.package.has(author_id=user.id))

	all_stats = query \
		.filter(PackageDailyStats.package.has(state=PackageState.APPROVED),
				PackageDailyStats.date >= start_date, PackageDailyStats.date <= end_date) \
		.order_by(db.asc(PackageDailyStats.package_id), db.asc(PackageDailyStats.date)) \
		.all()

	stats_by_package = {}
	for stat in all_stats:
		bucket = stats_by_package.get(stat.package_id, [])
		stats_by_package[stat.package_id] = bucket

		bucket.append(stat)

	package_title_by_id = {}
	pkg_query = user.packages if user else Package.query
	for package in pkg_query.filter_by(state=PackageState.APPROVED).all():
		if user:
			package_title_by_id[package.id] = package.title
		else:
			package_title_by_id[package.id] = package.get_id()

	result = {}

	for package_id, stats in stats_by_package.items():
		i = 0
		row = []
		result[package_title_by_id[package_id]] = row
		for date in daterange(start_date, end_date):
			if i >= len(stats):
				row.append(0)
				continue

			stat = stats[i]
			if stat.date == date:
				row.append(stat.downloads)
				i += 1
			elif stat.date > date:
				row.append(0)
			else:
				raise Exception(f"Invalid logic, expected stat {stat.date} to be later than {date}")

	return result


def get_all_package_stats(start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None):
	now_date = datetime.datetime.utcnow().date()
	if end_date is None or end_date > now_date:
		end_date = now_date

	min_start_date = (datetime.datetime.utcnow() - datetime.timedelta(days=29)).date()
	if start_date is None or start_date < min_start_date:
		start_date = min_start_date

	return {
		"start": start_date.isoformat(),
		"end": end_date.isoformat(),
		"package_downloads": get_package_overview_for_user(None, start_date, end_date),
	}
