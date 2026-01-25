"""empty message

Revision ID: 3eb4dc65ceab
Revises: 62bf1dcc2196
Create Date: 2026-01-25 14:56:59.099666

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3eb4dc65ceab'
down_revision = '62bf1dcc2196'
branch_labels = None
depends_on = None


def upgrade():
	status = postgresql.ENUM('NONE', 'ASSISTED', 'GENERATED', name='packageaidisclosure')
	status.create(op.get_bind())

	with op.batch_alter_table('package', schema=None) as batch_op:
		batch_op.add_column(sa.Column('ai_disclosure', sa.Enum('NONE', 'ASSISTED', 'GENERATED', name='packageaidisclosure'), nullable=True))


def downgrade():
	with op.batch_alter_table('package', schema=None) as batch_op:
		batch_op.drop_column('ai_disclosure')
