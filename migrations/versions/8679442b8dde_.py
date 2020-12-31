"""empty message

Revision ID: 8679442b8dde
Revises: f612e293070a
Create Date: 2020-07-11 00:14:02.330903

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8679442b8dde'
down_revision = 'f612e293070a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('thread', sa.Column('locked', sa.Boolean(), server_default='0', nullable=False))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('thread', 'locked')
    # ### end Alembic commands ###
