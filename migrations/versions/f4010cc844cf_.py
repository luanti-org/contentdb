"""empty message

Revision ID: f4010cc844cf
Revises: 16193066954b
Create Date: 2026-08-31 16:15:25.285669

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f4010cc844cf'
down_revision = '16193066954b'
branch_labels = None
depends_on = None


def upgrade():
    status = postgresql.ENUM('NEW', 'IGNORED', 'ACCEPTED', name='contentdetectionstate')
    status.create(op.get_bind())

    op.create_table('content_detection_dataset',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('content_detection_dataset_entry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=True),
    sa.Column('path', sa.String(length=200), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['content_detection_dataset.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('package_content_detection',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=True),
    sa.Column('content_path', sa.String(length=200), nullable=False),
    sa.Column('content_phash', sa.String(length=200), nullable=False),
    sa.Column('content_dhash', sa.String(length=200), nullable=False),
    sa.Column('match_path', sa.String(length=200), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('state', sa.Enum('NEW', 'IGNORED', 'ACCEPTED', name='contentdetectionstate'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['package_id'], ['package.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_package_content_detection_package_hash', 'package_content_detection',
        ['package_id', 'content_phash', 'content_dhash'])
    op.create_table('content_detection_dataset_entry_hash',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dataset_entry_id', sa.Integer(), nullable=True),
    sa.Column('phash', sa.String(length=200), nullable=False),
    sa.Column('dhash', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['dataset_entry_id'], ['content_detection_dataset_entry.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('content_detection_dataset_entry_hash')
    op.drop_index('ix_package_content_detection_package_hash', table_name='package_content_detection')
    op.drop_table('package_content_detection')
    op.drop_table('content_detection_dataset_entry')
    op.drop_table('content_detection_dataset')

    postgresql.ENUM(name='contentdetectionstate').drop(op.get_bind())
