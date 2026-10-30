"""empty message

Revision ID: b3c9e1f2a4d7
Revises: 7f1d81a28f25
Create Date: 2026-10-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b3c9e1f2a4d7'
down_revision = '7f1d81a28f25'
branch_labels = None
depends_on = None

def upgrade():
	op.add_column("package_release", sa.Column("file_sha256", sa.String(length=64), nullable=True))


def downgrade():
	op.drop_column("package_release", "file_sha256")
