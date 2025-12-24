"""empty message

Revision ID: 62bf1dcc2196
Revises: 06af23184d15
Create Date: 2025-12-24 14:24:39.612978

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '62bf1dcc2196'
down_revision = '06af23184d15'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approval_thread_stale', sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.drop_column('approval_thread_stale')
