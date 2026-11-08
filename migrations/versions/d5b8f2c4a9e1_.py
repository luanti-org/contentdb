"""Add user_session.reauthenticated_at

Revision ID: d5b8f2c4a9e1
Revises: c2a7e5d9f1b3
Create Date: 2026-11-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5b8f2c4a9e1'
down_revision = 'c2a7e5d9f1b3'
branch_labels = None
depends_on = None


def upgrade():
	op.add_column("user_session", sa.Column("reauthenticated_at", sa.DateTime(), nullable=True))


def downgrade():
	op.drop_column("user_session", "reauthenticated_at")
