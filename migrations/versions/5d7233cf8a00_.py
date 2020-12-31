"""empty message

Revision ID: 5d7233cf8a00
Revises: 81de25b72f66
Create Date: 2020-12-05 03:50:18.843494

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5d7233cf8a00'
down_revision = '81de25b72f66'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user_notification_preferences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('pref_other', sa.Integer(), nullable=False),
    sa.Column('pref_package_edit', sa.Integer(), nullable=False),
    sa.Column('pref_package_approval', sa.Integer(), nullable=False),
    sa.Column('pref_new_thread', sa.Integer(), nullable=False),
    sa.Column('pref_new_review', sa.Integer(), nullable=False),
    sa.Column('pref_thread_reply', sa.Integer(), nullable=False),
    sa.Column('pref_maintainer', sa.Integer(), nullable=False),
    sa.Column('pref_editor_alert', sa.Integer(), nullable=False),
    sa.Column('pref_editor_misc', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('user_notification_preferences')
    # ### end Alembic commands ###
