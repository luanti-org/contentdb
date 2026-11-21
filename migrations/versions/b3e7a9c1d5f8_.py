"""Replace the Approver rank with Curator

Approver was unused. Curator keeps its place in the rank order, so it's between Trusted Member and Editor, and the
permissions Approver had (approving packages, releases, and screenshots, seeing private threads, and so on) are now
Editor's, which already had them.

Revision ID: b3e7a9c1d5f8
Revises: a9d3f1c7e5b2
Create Date: 2026-11-22 16:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b3e7a9c1d5f8'
down_revision = 'a9d3f1c7e5b2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE userrank RENAME VALUE 'APPROVER' TO 'CURATOR'")


def downgrade():
    op.execute("ALTER TYPE userrank RENAME VALUE 'CURATOR' TO 'APPROVER'")
