"""Remove email_subscription.token, unsubscribe links are signed instead

Revision ID: d7f2b3c5e1a4
Revises: c4e8a1d2b9f3
Create Date: 2026-10-31 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd7f2b3c5e1a4'
down_revision = 'c4e8a1d2b9f3'
branch_labels = None
depends_on = None


def upgrade():
	op.drop_column("email_subscription", "token")


def downgrade():
	op.add_column("email_subscription", sa.Column("token", sa.String(length=32), nullable=True))
