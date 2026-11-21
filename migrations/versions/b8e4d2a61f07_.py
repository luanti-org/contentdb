"""Add tag kind and package types

Revision ID: b8e4d2a61f07
Revises: 5e2a9c7d3b18
Create Date: 2026-11-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'b8e4d2a61f07'
down_revision = '5e2a9c7d3b18'
branch_labels = None
depends_on = None


def upgrade():
    tag_kind = postgresql.ENUM('FEATURE', 'CATEGORY', name='tagkind')
    tag_kind.create(op.get_bind())
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.Enum('FEATURE', 'CATEGORY', name='tagkind'), nullable=False,
                server_default='FEATURE'))
        # packagetype already exists, from package.type
        package_type = postgresql.ENUM('MOD', 'GAME', 'TXP', name='packagetype', create_type=False)
        batch_op.add_column(sa.Column('package_types', postgresql.ARRAY(package_type), nullable=False,
                server_default='{}'))


def downgrade():
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.drop_column('package_types')
        batch_op.drop_column('kind')

    sa.Enum(name='tagkind').drop(op.get_bind(), checkfirst=True)
