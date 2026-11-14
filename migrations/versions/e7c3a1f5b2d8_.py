"""Add user_session.ip_address and user_agent

Revision ID: e7c3a1f5b2d8
Revises: d5b8f2c4a9e1
Create Date: 2026-11-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e7c3a1f5b2d8'
down_revision = 'd5b8f2c4a9e1'
branch_labels = None
depends_on = None


def upgrade():
	op.add_column("user_session", sa.Column("ip_address", sa.String(length=45), nullable=True))
	op.add_column("user_session", sa.Column("user_agent", sa.String(length=512), nullable=True))


def downgrade():
	op.drop_column("user_session", "user_agent")
	op.drop_column("user_session", "ip_address")
