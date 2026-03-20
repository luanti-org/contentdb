"""empty message

Revision ID: d0e41ca50db9
Revises: 0d546ed02109
Create Date: 2026-03-20 18:14:54.035176

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd0e41ca50db9'
down_revision = '0d546ed02109'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sensitive_package', sa.Boolean(), nullable=False, server_default="false"))

    with op.batch_alter_table('package_review', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approved', sa.Boolean(), nullable=False, server_default="true"))


def downgrade():
    with op.batch_alter_table('package_review', schema=None) as batch_op:
        batch_op.drop_column('approved')

    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.drop_column('sensitive_package')
