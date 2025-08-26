"""empty message

Revision ID: 1e08d7e4c15d
Revises: 9689a71efe88
Create Date: 2025-08-26 14:43:30.501823

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1e08d7e4c15d'
down_revision = '9689a71efe88'
branch_labels = None
depends_on = None


def upgrade():
    status = postgresql.ENUM('ACCOUNT_DELETION', 'COPYRIGHT', 'USER_CONDUCT', 'ILLEGAL_HARMFUL', 'APPEAL', 'OTHER', name='reportcategory')
    status.create(op.get_bind())
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.Enum('ACCOUNT_DELETION', 'COPYRIGHT', 'USER_CONDUCT', 'ILLEGAL_HARMFUL', 'APPEAL', 'OTHER', name='reportcategory'), nullable=False, server_default="OTHER"))


def downgrade():
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.drop_column('category')
