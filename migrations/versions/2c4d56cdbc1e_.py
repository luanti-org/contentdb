"""empty message

Revision ID: 2c4d56cdbc1e
Revises: d0e41ca50db9
Create Date: 2026-05-26 22:32:15.270013

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2c4d56cdbc1e'
down_revision = 'd0e41ca50db9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package_daily_stats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('views_luanti', sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column('downloads_v510', sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table('package_daily_stats', schema=None) as batch_op:
        batch_op.drop_column('views_luanti')
        batch_op.drop_column('downloads_v510')
