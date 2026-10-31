"""Add user.old_password for forced password resets

Revision ID: d7a3c5e9f1b2
Revises: a6c3e9b1f4d5
Create Date: 2026-10-31 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd7a3c5e9f1b2'
down_revision = 'a6c3e9b1f4d5'
branch_labels = None
depends_on = None


def upgrade():
	op.add_column("user", sa.Column("old_password", sa.String(length=255), nullable=True))


def downgrade():
	op.drop_column("user", "old_password")
