"""empty message

Revision ID: f94192c54b73
Revises: 97f9d84aae1e
Create Date: 2025-11-08 13:34:18.185232

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f94192c54b73'
down_revision = '97f9d84aae1e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(text("ALTER TYPE releasestate ADD VALUE 'UNAPPROVED' AFTER 'APPROVED'"))


def downgrade():
    pass
