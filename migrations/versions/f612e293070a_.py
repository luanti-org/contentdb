"""empty message

Revision ID: f612e293070a
Revises: 019da77ba02d
Create Date: 2020-07-10 23:32:02.465374

"""
from alembic import op
import sqlalchemy as sa
import datetime

# revision identifiers, used by Alembic.
revision = 'f612e293070a'
down_revision = '019da77ba02d'
branch_labels = None
depends_on = None


def upgrade():
	# ### commands auto generated by Alembic - please adjust! ###
	op.add_column('notification', sa.Column('created_at', sa.DateTime(), nullable=True, server_default=datetime.datetime.utcnow().isoformat()))
	op.add_column('notification', sa.Column('package_id', sa.Integer(), nullable=True))
	op.alter_column('notification', 'causer_id',
			   existing_type=sa.INTEGER(),
			   nullable=False)
	op.alter_column('notification', 'user_id',
			   existing_type=sa.INTEGER(),
			   nullable=False)
	op.create_foreign_key(None, 'notification', 'package', ['package_id'], ['id'])
	# ### end Alembic commands ###


def downgrade():
	# ### commands auto generated by Alembic - please adjust! ###
	op.drop_constraint(None, 'notification', type_='foreignkey')
	op.alter_column('notification', 'user_id',
			   existing_type=sa.INTEGER(),
			   nullable=True)
	op.alter_column('notification', 'causer_id',
			   existing_type=sa.INTEGER(),
			   nullable=True)
	op.drop_column('notification', 'package_id')
	# ### end Alembic commands ###
