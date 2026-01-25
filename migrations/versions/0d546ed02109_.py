"""empty message

Revision ID: 0d546ed02109
Revises: 3eb4dc65ceab
Create Date: 2026-01-25 15:45:40.288059

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0d546ed02109'
down_revision = '3eb4dc65ceab'
branch_labels = None
depends_on = None


def upgrade():
	op.execute(text("ALTER TYPE packageaidisclosure ADD VALUE 'UNKNOWN' BEFORE 'NONE'"))
	op.execute(text("COMMIT"))
	op.execute(text("UPDATE package SET ai_disclosure='UNKNOWN' WHERE ai_disclosure IS NULL"))
	with op.batch_alter_table('package', schema=None) as batch_op:
		batch_op.alter_column("ai_disclosure",
				existing_type=sa.Enum('UNKNOWN', 'NONE', 'ASSISTED', 'GENERATED', name='packageaidisclosure'),
				nullable=False)


def downgrade():
	with op.batch_alter_table('package', schema=None) as batch_op:
		batch_op.alter_column("ai_disclosure",
				existing_type= sa.Enum('NONE', 'ASSISTED', 'GENERATED', name='packageaidisclosure'),
				nullable=True)

	op.execute(text("UPDATE package SET ai_disclosure=NULL WHERE ai_disclosure = 'UNKNOWN'"))
