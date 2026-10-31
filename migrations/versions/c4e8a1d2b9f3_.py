"""Drop unused github_access_token and reset_password_token

Revision ID: c4e8a1d2b9f3
Revises: b8d4f2a6c1e3
Create Date: 2026-10-31 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4e8a1d2b9f3'
down_revision = 'b8d4f2a6c1e3'
branch_labels = None
depends_on = None


def upgrade():
	op.drop_column("user", "github_access_token")
	op.drop_column("user", "reset_password_token")


def downgrade():
	op.add_column("user", sa.Column("reset_password_token", sa.String(length=100), nullable=False, server_default=""))
	op.add_column("user", sa.Column("github_access_token", sa.String(length=50), nullable=True))
