"""Hash API tokens

Revision ID: f1b5d8e2a7c6
Revises: e3a9c6f4d2b8
Create Date: 2026-10-31 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f1b5d8e2a7c6'
down_revision = 'e3a9c6f4d2b8'
branch_labels = None
depends_on = None

# Existing tokens get a random hash, so they can't be used until they are reset
RANDOM_HASH = "encode(sha256(gen_random_uuid()::text::bytea), 'hex')"


def upgrade():
	op.drop_column("api_token", "access_token")
	op.add_column("api_token", sa.Column("access_token_hash", sa.String(length=64), nullable=True))
	op.execute(f"UPDATE api_token SET access_token_hash = {RANDOM_HASH}")
	op.alter_column("api_token", "access_token_hash", nullable=False)
	op.create_unique_constraint("api_token_access_token_hash_key", "api_token", ["access_token_hash"])


def downgrade():
	op.drop_column("api_token", "access_token_hash")
	op.add_column("api_token", sa.Column("access_token", sa.String(length=34), nullable=True))
	op.execute("UPDATE api_token SET access_token = left(md5(gen_random_uuid()::text), 32)")
	op.alter_column("api_token", "access_token", nullable=False)
	op.create_unique_constraint("api_token_access_token_key", "api_token", ["access_token"])
