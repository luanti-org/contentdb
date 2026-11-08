"""Add pending_user_deletion

Revision ID: c2a7e5d9f1b3
Revises: b7d4f1e9a2c6
Create Date: 2026-11-07 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c2a7e5d9f1b3'
down_revision = 'b7d4f1e9a2c6'
branch_labels = None
depends_on = None


def upgrade():
	op.create_table("pending_user_deletion",
		sa.Column("user_id", sa.Integer(), nullable=False),
		sa.Column("reason", sa.Enum("REQUESTED", "INACTIVE", name="userdeletionreason"), nullable=False),
		sa.Column("created_at", sa.DateTime(), nullable=False),
		sa.Column("delete_at", sa.DateTime(), nullable=False),
		sa.Column("reminder_sent_at", sa.DateTime(), nullable=True),
		sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("user_id"))
	op.create_index(op.f("ix_pending_user_deletion_delete_at"), "pending_user_deletion", ["delete_at"], unique=False)


def downgrade():
	op.drop_index(op.f("ix_pending_user_deletion_delete_at"), table_name="pending_user_deletion")
	op.drop_table("pending_user_deletion")
	sa.Enum(name="userdeletionreason").drop(op.get_bind(), checkfirst=True)
