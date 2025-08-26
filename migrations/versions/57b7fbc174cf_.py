"""empty message

Revision ID: 57b7fbc174cf
Revises: 1e08d7e4c15d
Create Date: 2025-08-26 19:23:22.446424

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '57b7fbc174cf'
down_revision = '1e08d7e4c15d'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(text("COMMIT"))
    op.execute(text("ALTER TYPE reportcategory ADD VALUE 'REVIEW' AFTER 'ILLEGAL_HARMFUL'"))


def downgrade():
    pass
