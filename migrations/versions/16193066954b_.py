"""empty message

Revision ID: 16193066954b
Revises: 4d1cf83c0c53
Create Date: 2026-08-25 17:48:00.034900

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '16193066954b'
down_revision = '4d1cf83c0c53'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.add_column(sa.Column('insecure_env_justification', sa.Unicode(length=100), nullable=True, default=None))
        batch_op.add_column(sa.Column('http_api_justification', sa.Unicode(length=100), nullable=True, default=None))

    with op.batch_alter_table('package_release', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uses_insecure_env', sa.Boolean(), nullable=True, default=None))
        batch_op.add_column(sa.Column('uses_http_api', sa.Boolean(), nullable=True, default=None))


def downgrade():
    with op.batch_alter_table('package_release', schema=None) as batch_op:
        batch_op.drop_column('uses_http_api')
        batch_op.drop_column('uses_insecure_env')

    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.drop_column('http_api_justification')
        batch_op.drop_column('insecure_env_justification')
