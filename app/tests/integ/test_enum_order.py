# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from sqlalchemy import text

from app.models import db, User, UserRank
from .utils import client # noqa


def get_db_enum_order(type_name: str) -> list[str]:
	return list(db.session.execute(text("""
		SELECT e.enumlabel FROM pg_enum e
		JOIN pg_type t ON t.oid = e.enumtypid
		WHERE t.typname = :name
		ORDER BY e.enumsortorder
	"""), {"name": type_name}).scalars().all())


def test_user_rank_enum_order(client):
	"""
	Postgres compares enum values by declared order, so queries like `User.rank >= UserRank.MODERATOR`
	are only correct if the database order matches UserRank.value. When adding a rank in a migration,
	use `ALTER TYPE userrank ADD VALUE 'X' BEFORE/AFTER 'Y'`.
	"""
	expected = [x.name for x in sorted(UserRank, key=lambda x: x.value)]
	assert get_db_enum_order("userrank") == expected


def test_user_rank_sql_comparison(client):
	for rank in UserRank:
		db.session.add(User(f"rank_{rank.name.lower()}"))
	db.session.flush()
	for user in User.query.filter(User.username.like("rank\\_%")).all():
		user.rank = UserRank[user.username[5:].upper()]
	db.session.flush()

	at_least_mod = User.query.filter(User.username.like("rank\\_%"), User.rank >= UserRank.MODERATOR).all()
	assert sorted(x.rank.name for x in at_least_mod) == ["ADMIN", "MODERATOR"]
