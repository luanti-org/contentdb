"""Use citext for usernames and emails, so they're compared and unique ignoring case

Production already had the username columns as citext, changed outside of migrations. This makes every database match,
and adds the email columns.

Revision ID: b4e8d2a6c1f3
Revises: 897861619743
Create Date: 2026-11-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b4e8d2a6c1f3'
down_revision = '897861619743'
branch_labels = None
depends_on = None


# (table, column, type before this migration on databases built from migrations)
COLUMNS = [
	("user", "username", "VARCHAR(50)"),
	("user", "github_username", "VARCHAR(50)"),
	("user", "forums_username", "VARCHAR(50)"),
	("user", "email", "VARCHAR(255)"),
	("email_subscription", "email", "VARCHAR(100)"),
	("user_email_verification", "email", "VARCHAR(100)"),
]

# Unique columns where values that differ only by case must be fixed by hand. email_subscription is merged instead.
UNIQUE_USER_COLUMNS = ["username", "github_username", "forums_username", "email"]


def is_citext(conn, table, column):
	return conn.execute(sa.text("""
		SELECT udt_name = 'citext' FROM information_schema.columns
		WHERE table_schema = current_schema() AND table_name = :table AND column_name = :column
	"""), {"table": table, "column": column}).scalar()


def upgrade():
	conn = op.get_bind()

	# Trusted extension, so the database owner can create it
	op.execute("CREATE EXTENSION IF NOT EXISTS citext")

	# Users that differ only by case can't be merged automatically, they need to be resolved by hand
	problems = []
	for column in UNIQUE_USER_COLUMNS:
		duplicates = conn.execute(sa.text(f"""
			SELECT lower({column}), string_agg(username, ', ' ORDER BY id)
			FROM "user"
			WHERE {column} IS NOT NULL
			GROUP BY lower({column})
			HAVING count(*) > 1
		""")).fetchall()
		problems.extend(f"  {column} {value}: {usernames}" for value, usernames in duplicates)

	if problems:
		lines = "\n".join(problems)
		raise Exception("These users have the same value with different casing. "
				f"Change or remove it on all but one of each before running this migration:\n{lines}")

	# Merge email subscriptions that differ only by case, keeping the oldest. The address stays blacklisted if any
	# of them were.
	conn.execute(sa.text("""
		UPDATE email_subscription AS keep
		SET blacklisted = dupes.blacklisted
		FROM (
			SELECT min(id) AS id, bool_or(blacklisted) AS blacklisted
			FROM email_subscription
			GROUP BY lower(email)
			HAVING count(*) > 1
		) AS dupes
		WHERE keep.id = dupes.id
	"""))
	conn.execute(sa.text("""
		DELETE FROM email_subscription
		WHERE id NOT IN (SELECT min(id) FROM email_subscription GROUP BY lower(email))
	"""))

	# Existing unique constraints are rebuilt with the new type, so they start ignoring case
	for table, column, _ in COLUMNS:
		if not is_citext(conn, table, column):
			op.execute(f'ALTER TABLE "{table}" ALTER COLUMN {column} TYPE citext')


def downgrade():
	# The username columns are left as citext, as production had them before this migration
	for table, column, old_type in COLUMNS:
		if "username" not in column:
			op.execute(f'ALTER TABLE "{table}" ALTER COLUMN {column} TYPE {old_type}')
