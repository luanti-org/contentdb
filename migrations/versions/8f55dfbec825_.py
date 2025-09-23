"""empty message

Revision ID: 8f55dfbec825
Revises: 242fd82077bb
Create Date: 2025-09-23 15:21:06.445012

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '8f55dfbec825'
down_revision = '242fd82077bb'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(text("COMMIT"))
    op.execute(text("ALTER TYPE reportcategory ADD VALUE 'SPAM' AFTER 'USER_CONDUCT'"))


def downgrade():
    pass
