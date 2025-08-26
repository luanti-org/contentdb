"""empty message

Revision ID: 1acc6e90bbac
Revises: 57b7fbc174cf
Create Date: 2025-08-26 20:23:29.086541

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1acc6e90bbac'
down_revision = '57b7fbc174cf'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package_update_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_checked_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('package_update_config', schema=None) as batch_op:
        batch_op.drop_column('last_checked_at')
