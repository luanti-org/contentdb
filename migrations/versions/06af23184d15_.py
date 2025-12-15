"""empty message

Revision ID: 06af23184d15
Revises: e02ce7e98d92
Create Date: 2025-12-15 18:40:13.829344

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '06af23184d15'
down_revision = 'e02ce7e98d92'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.add_column(sa.Column('read_at', sa.DateTime(), nullable=True, default=None))


def downgrade():
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.drop_column('read_at')
