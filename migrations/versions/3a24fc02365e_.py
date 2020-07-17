"""empty message

Revision ID: 3a24fc02365e
Revises: b370c3eb4227
Create Date: 2020-07-17 20:58:31.130449

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a24fc02365e'
down_revision = 'b370c3eb4227'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('tag', sa.Column('description', sa.String(length=500), nullable=True, server_default=None))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('tag', 'description')
    # ### end Alembic commands ###
