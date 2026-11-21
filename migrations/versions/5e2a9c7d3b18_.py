"""Add Gravatar setting to users, and opt in users from before Gravatar was removed

Revision ID: 5e2a9c7d3b18
Revises: 8d4b2e6f1a93
Create Date: 2026-11-21 16:00:00.000000

"""
import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5e2a9c7d3b18'
down_revision = '8d4b2e6f1a93'
branch_labels = None
depends_on = None


# Users who registered before this had Gravatar until it was removed on 2026-10-31, so are opted in
OPT_IN_REGISTERED_BEFORE = datetime.datetime(2026, 10, 26)


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('use_gravatar', sa.Boolean(), nullable=False, server_default='false'))

    # Older accounts have no created_at. An empty profile_pic means no picture, as in get_profile_pic_url() and
    # check_forum_account(). Users with a profile picture are left out, as users now choose either a
    # profile picture or Gravatar. Users without an email are left out, as it would do nothing until they added one.
    op.execute(f"""
        UPDATE "user" SET use_gravatar = true
        WHERE (created_at IS NULL OR created_at < '{OPT_IN_REGISTERED_BEFORE.isoformat()}')
            AND email IS NOT NULL
            AND (profile_pic IS NULL OR profile_pic = '')
    """)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('use_gravatar')
