"""empty message

Revision ID: 97f9d84aae1e
Revises: 8f55dfbec825
Create Date: 2025-11-08 12:36:07.409144

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '97f9d84aae1e'
down_revision = '8f55dfbec825'
branch_labels = None
depends_on = None


def upgrade():
    status = postgresql.ENUM('PROCESSING', 'APPROVED', 'FAILED', 'ARCHIVED', name='releasestate')
    status.create(op.get_bind())

    op.add_column("package_release", sa.Column('state', sa.Enum('PROCESSING', 'APPROVED', 'FAILED', 'ARCHIVED', name='releasestate'), nullable=True))
    with op.batch_alter_table('package_release', schema=None) as batch_op:
        batch_op.execute("UPDATE package_release SET state = 'APPROVED' WHERE approved;")
        batch_op.execute("UPDATE package_release SET state = 'FAILED' WHERE NOT approved;")
        batch_op.alter_column(
            'state',
            nullable=False,
        )
        batch_op.drop_constraint("CK_approval_valid", type_="check")
        batch_op.create_check_constraint("CK_approval_valid",
                                         "state != 'APPROVED' OR (task_id IS NULL AND url != '')")
        batch_op.drop_column('approved')


def downgrade():
    with op.batch_alter_table('package_release', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approved', sa.BOOLEAN(), autoincrement=False, nullable=False))
        batch_op.drop_constraint("CK_approval_valid", type_="check")
        batch_op.create_check_constraint("CK_approval_valid", "not approved OR (task_id IS NULL AND NOT url = '')")
        batch_op.drop_column('state')
