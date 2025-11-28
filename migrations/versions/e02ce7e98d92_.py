"""empty message

Revision ID: e02ce7e98d92
Revises: f94192c54b73
Create Date: 2025-11-28 20:16:32.330157
"""

from alembic import op
import sqlalchemy as sa

revision = 'e02ce7e98d92'
down_revision = 'f94192c54b73'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package_update_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_id', sa.String(length=37), nullable=True))


def downgrade():
    with op.batch_alter_table('package_update_config', schema=None) as batch_op:
        batch_op.drop_column('task_id')
