"""empty message

Revision ID: c181c6c88bae
Revises: daa040b727b2
Create Date: 2025-07-02 17:21:33.554960

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c181c6c88bae'
down_revision = 'daa040b727b2'
branch_labels = None
depends_on = None


def upgrade():
	op.add_column('package_release',
			sa.Column('file_size_bytes', sa.Integer(), nullable=False, server_default="0"))
	op.add_column('package_screenshot',
			sa.Column('file_size_bytes', sa.Integer(), nullable=False, server_default="0"))


def downgrade():
	op.drop_column('package', 'file_size_bytes')
	op.drop_column('package_screenshot', 'file_size_bytes')
