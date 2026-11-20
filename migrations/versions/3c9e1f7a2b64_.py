"""Add dashboard widget slides

Revision ID: 3c9e1f7a2b64
Revises: fa25785307b1
Create Date: 2026-11-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3c9e1f7a2b64'
down_revision = 'fa25785307b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dashboard_widget_slide',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('widget_id', sa.Integer(), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('label', sa.String(length=50), nullable=True),
    sa.Column('url', sa.String(length=512), nullable=False),
    sa.Column('image_path', sa.String(length=200), nullable=False),
    sa.Column('starts_at', sa.DateTime(), nullable=True),
    sa.Column('ends_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['widget_id'], ['dashboard_widget.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('dashboard_widget_slide')
