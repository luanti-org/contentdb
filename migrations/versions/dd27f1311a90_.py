"""empty message

Revision ID: dd27f1311a90
Revises: c141a63b2487
Create Date: 2020-07-09 00:20:39.501355

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dd27f1311a90'
down_revision = 'c141a63b2487'
branch_labels = None
depends_on = None


def upgrade():
	# ### commands auto generated by Alembic - please adjust! ###
	op.add_column('package', sa.Column('score_downloads', sa.Float(), nullable=False, server_default="0"))
	op.execute("""
		UPDATE "package" SET "score_downloads"="score";
	""")
	# ### end Alembic commands ###


def downgrade():
	# ### commands auto generated by Alembic - please adjust! ###
	op.drop_column('package', 'score_downloads')
	# ### end Alembic commands ###
