"""Add collage images to tags

Revision ID: e7a3c5d9b2f4
Revises: c4f1a9e2d7b3
Create Date: 2026-11-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7a3c5d9b2f4'
down_revision = 'c4f1a9e2d7b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.add_column(sa.Column('collage_path', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.drop_column('collage_path')
