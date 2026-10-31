"""Require audit log URLs to be paths

Revision ID: b8d4f2a6c1e3
Revises: b3c9e1f2a4d7
Create Date: 2026-10-31 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b8d4f2a6c1e3'
down_revision = 'b3c9e1f2a4d7'
branch_labels = None
depends_on = None


def upgrade():
	op.execute(r"""
		UPDATE audit_log_entry
		SET url = regexp_replace(url, '^https?://content\.(minetest\.net|luanti\.org)(?=/)', '')
		WHERE url ~ '^https?://content\.(minetest\.net|luanti\.org)/'
	""")

	# Fail with a clear message rather than a constraint violation
	conn = op.get_bind()
	invalid = conn.execute(sa.text("""
		SELECT id, url FROM audit_log_entry
		WHERE url IS NOT NULL AND (url NOT LIKE '/%' OR url LIKE '//%')
		ORDER BY id LIMIT 10
	""")).fetchall()
	if invalid:
		examples = ", ".join(f"{row.id}: {row.url}" for row in invalid)
		raise Exception(f"Audit log entries have URLs that aren't paths, fix them manually: {examples}")

	op.create_check_constraint("url_is_path", "audit_log_entry",
			"url IS NULL OR (url LIKE '/%' AND url NOT LIKE '//%')")


def downgrade():
	op.drop_constraint("url_is_path", "audit_log_entry", type_="check")
