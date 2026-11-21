"""Add email bounce tracking to email subscriptions

Revision ID: 8d4b2e6f1a93
Revises: 3c9e1f7a2b64
Create Date: 2026-11-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8d4b2e6f1a93'
down_revision = '3c9e1f7a2b64'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('email_subscription', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bounced_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('bounce_reason', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('bounce_cleared_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('email_subscription', schema=None) as batch_op:
        batch_op.drop_column('bounce_cleared_at')
        batch_op.drop_column('bounce_reason')
        batch_op.drop_column('bounced_at')
