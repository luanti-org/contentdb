"""empty message

Revision ID: 7f1d81a28f25
Revises: 16193066954b
Create Date: 2026-09-28 19:07:04.110357

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7f1d81a28f25'
down_revision = '16193066954b'
branch_labels = None
depends_on = None

def upgrade():
	op.alter_column(
		"package_release", "url",
		new_column_name="upload_path",
		existing_type=sa.String(length=200),
		existing_nullable=False,
	)
	op.alter_column(
		"package_screenshot", "url",
		new_column_name="upload_path",
		existing_type=sa.String(length=100),
		existing_nullable=False,
	)
	op.alter_column(
		"report_attachment", "url",
		new_column_name="upload_path",
		existing_type=sa.String(length=100),
		existing_nullable=False,
	)


def downgrade():
	op.alter_column(
		"package_screenshot", "upload_path",
		new_column_name="url",
		existing_type=sa.String(length=100),
		existing_nullable=False,
	)
	op.alter_column(
		"package_release", "upload_path",
		new_column_name="url",
		existing_type=sa.String(length=200),
		existing_nullable=False,
	)
	op.alter_column(
		"report_attachment", "upload_path",
		new_column_name="url",
		existing_type=sa.String(length=200),
		existing_nullable=False,
	)
