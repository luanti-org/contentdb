"""Hash email verification tokens

Revision ID: e3a9c6f4d2b8
Revises: d7f2b3c5e1a4
Create Date: 2026-10-31 12:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e3a9c6f4d2b8'
down_revision = 'd7f2b3c5e1a4'
branch_labels = None
depends_on = None


def upgrade():
	# Pending verifications expire after 12 hours anyway
	op.execute("DELETE FROM user_email_verification")
	op.drop_column("user_email_verification", "token")
	op.add_column("user_email_verification", sa.Column("token_hash", sa.String(length=64), nullable=True))
	op.create_unique_constraint("user_email_verification_token_hash_key", "user_email_verification", ["token_hash"])


def downgrade():
	op.drop_column("user_email_verification", "token_hash")
	op.add_column("user_email_verification", sa.Column("token", sa.String(length=32), nullable=True))
