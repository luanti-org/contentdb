"""empty message

Revision ID: 242fd82077bb
Revises: 1acc6e90bbac
Create Date: 2025-09-01 10:00:39.263576

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '242fd82077bb'
down_revision = '1acc6e90bbac'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('report_attachment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('report_id', sa.String(length=24), nullable=False),
    sa.Column('url', sa.String(length=100), nullable=False),
    sa.ForeignKeyConstraint(['report_id'], ['report.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('report_attachment')
