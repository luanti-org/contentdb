from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '663521dfe86d'
down_revision = 'c181c6c88bae'
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("minetest_release", "luanti_release")


def downgrade():
    op.rename_table("luanti_release", "minetest_release")
