"""Make forum_topic.discarded, forum_topic.type, and package.type not null, as the models declare

The migrations that created these columns made them nullable, so every database had them nullable, unlike the
models. Production had no nulls in any of them when this was written.

Revision ID: c865b2a6ce1e
Revises: e7a3c5d9b2f4
Create Date: 2026-11-21 18:37:13.343905

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c865b2a6ce1e'
down_revision = 'e7a3c5d9b2f4'
branch_labels = None
depends_on = None


def upgrade():
    # Rows from before the column had a default, on databases other than production
    op.execute("UPDATE forum_topic SET discarded = false WHERE discarded IS NULL")

    with op.batch_alter_table('forum_topic', schema=None) as batch_op:
        batch_op.alter_column('discarded',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('false'))
        batch_op.alter_column('type',
               existing_type=postgresql.ENUM('MOD', 'GAME', 'TXP', name='packagetype'),
               nullable=False)

    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.alter_column('type',
               existing_type=postgresql.ENUM('MOD', 'GAME', 'TXP', name='packagetype'),
               nullable=False)


def downgrade():
    with op.batch_alter_table('package', schema=None) as batch_op:
        batch_op.alter_column('type',
               existing_type=postgresql.ENUM('MOD', 'GAME', 'TXP', name='packagetype'),
               nullable=True)

    with op.batch_alter_table('forum_topic', schema=None) as batch_op:
        batch_op.alter_column('type',
               existing_type=postgresql.ENUM('MOD', 'GAME', 'TXP', name='packagetype'),
               nullable=True)
        batch_op.alter_column('discarded',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('false'))
