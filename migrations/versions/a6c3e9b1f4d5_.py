"""Hash OAuth client secrets and auth codes

Revision ID: a6c3e9b1f4d5
Revises: f1b5d8e2a7c6
Create Date: 2026-10-31 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a6c3e9b1f4d5'
down_revision = 'f1b5d8e2a7c6'
branch_labels = None
depends_on = None

# Existing secrets get a random hash, so they can't be used until they are reset
RANDOM_HASH = "encode(sha256(gen_random_uuid()::text::bytea), 'hex')"


def upgrade():
	op.drop_column("api_token", "auth_code")
	op.add_column("api_token", sa.Column("auth_code_hash", sa.String(length=64), nullable=True))
	op.create_unique_constraint("api_token_auth_code_hash_key", "api_token", ["auth_code_hash"])

	op.drop_column("oauth_client", "secret")
	op.add_column("oauth_client", sa.Column("secret_hash", sa.String(length=64), nullable=True))
	op.execute(f"UPDATE oauth_client SET secret_hash = {RANDOM_HASH}")
	op.alter_column("oauth_client", "secret_hash", nullable=False)
	op.create_unique_constraint("oauth_client_secret_hash_key", "oauth_client", ["secret_hash"])


def downgrade():
	op.drop_column("oauth_client", "secret_hash")
	op.add_column("oauth_client", sa.Column("secret", sa.String(length=32), nullable=True))
	op.execute("UPDATE oauth_client SET secret = left(md5(gen_random_uuid()::text), 32)")
	op.alter_column("oauth_client", "secret", nullable=False)

	op.drop_column("api_token", "auth_code_hash")
	op.add_column("api_token", sa.Column("auth_code", sa.String(length=34), nullable=True))
	op.create_unique_constraint("api_token_auth_code_key", "api_token", ["auth_code"])
