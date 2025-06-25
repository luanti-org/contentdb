"""empty message

Revision ID: d52f6901b707
Revises: daa040b727b2
Create Date: 2024-10-22 21:18:23.929298

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd52f6901b707'
down_revision = 'daa040b727b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package_daily_stats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('views_minetest', sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column('v510', sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table('package_daily_stats', schema=None) as batch_op:
        batch_op.drop_column('views_minetest')
        batch_op.drop_column('v510')
