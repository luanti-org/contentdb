"""Add user_session, used as the Flask-Login session ID

Revision ID: 897861619743
Revises: d7a3c5e9f1b2
Create Date: 2026-11-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '897861619743'
down_revision = 'd7a3c5e9f1b2'
branch_labels = None
depends_on = None


def upgrade():
	op.create_table("user_session",
		sa.Column("id", sa.Integer(), nullable=False),
		sa.Column("user_id", sa.Integer(), nullable=False),
		sa.Column("token_hash", sa.String(length=64), nullable=False),
		sa.Column("created_at", sa.DateTime(), nullable=False),
		sa.Column("last_used_at", sa.DateTime(), nullable=False),
		sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint("token_hash"),
	)
	op.create_index(op.f("ix_user_session_user_id"), "user_session", ["user_id"], unique=False)


def downgrade():
	op.drop_index(op.f("ix_user_session_user_id"), table_name="user_session")
	op.drop_table("user_session")
