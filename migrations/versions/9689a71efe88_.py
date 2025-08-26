"""empty message

Revision ID: 9689a71efe88
Revises: 3052712496e4
Create Date: 2025-08-26 14:24:02.045713

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9689a71efe88'
down_revision = '3052712496e4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               type_=sa.String(length=24),
               existing_nullable=False)


def downgrade():
   with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.String(length=24),
               type_=sa.INTEGER(),
               existing_nullable=False)
