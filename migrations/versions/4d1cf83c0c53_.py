"""empty message

Revision ID: 4d1cf83c0c53
Revises: 2c4d56cdbc1e
Create Date: 2026-08-13 15:38:38.118914

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4d1cf83c0c53'
down_revision = '2c4d56cdbc1e'
branch_labels = None
depends_on = None



def upgrade():
	op.create_check_constraint("username_valid", "user", "username ~* '^[A-Za-z0-9 ._-]+$'")


def downgrade():
	op.drop_constraint("username_valid", "user", type_="check")
