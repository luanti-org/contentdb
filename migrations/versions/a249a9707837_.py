"""Repair userrank enum order on databases built from migrations

Postgres compares enum values by their declared order, not by UserRank.value.
TRUSTED_MEMBER and BANNED used to be appended to the end of the type, so
databases built by replaying migrations had them sorting after ADMIN. This
breaks queries such as `User.rank >= UserRank.MODERATOR`.

Databases that already have the correct order (such as production) are left
untouched.

Revision ID: a249a9707837
Revises: e3a9c6f4d2b8
Create Date: 2026-11-01 00:00:00.000000

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'a249a9707837'
down_revision = 'e3a9c6f4d2b8'
branch_labels = None
depends_on = None


EXPECTED_ORDER = [
	"BANNED",
	"NOT_JOINED",
	"NEW_MEMBER",
	"MEMBER",
	"TRUSTED_MEMBER",
	"APPROVER",
	"EDITOR",
	"BOT",
	"MODERATOR",
	"ADMIN",
]


def upgrade():
	conn = op.get_bind()

	current = conn.execute(text("""
		SELECT e.enumlabel FROM pg_enum e
		JOIN pg_type t ON t.oid = e.enumtypid
		WHERE t.typname = 'userrank'
		ORDER BY e.enumsortorder
	""")).scalars().all()

	if current == EXPECTED_ORDER:
		return

	if sorted(current) != sorted(EXPECTED_ORDER):
		raise Exception(f"Unexpected userrank values, refusing to rebuild: {current}")

	columns = conn.execute(text("""
		SELECT c.relname, a.attname FROM pg_attribute a
		JOIN pg_class c ON c.oid = a.attrelid
		WHERE a.atttypid = 'userrank'::regtype AND NOT a.attisdropped AND c.relkind = 'r'
	""")).all()

	labels = ", ".join(f"'{x}'" for x in EXPECTED_ORDER)
	op.execute("ALTER TYPE userrank RENAME TO userrank_old")
	op.execute(f"CREATE TYPE userrank AS ENUM ({labels})")
	for table, column in columns:
		op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE userrank USING "{column}"::text::userrank')
	op.execute("DROP TYPE userrank_old")


def downgrade():
	pass
