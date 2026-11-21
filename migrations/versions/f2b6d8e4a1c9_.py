"""Add icons to tags, and give the categories theirs

Revision ID: f2b6d8e4a1c9
Revises: c865b2a6ce1e
Create Date: 2026-11-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b6d8e4a1c9'
down_revision = 'c865b2a6ce1e'
branch_labels = None
depends_on = None


# Font Awesome 5 icons for the categories added by c4f1a9e2d7b3_.py
CATEGORY_ICONS = {
    "category_survival": "fa-campground",
    "category_creative": "fa-cubes",
    "category_adventure": "fa-dragon",
    "category_puzzle": "fa-puzzle-piece",
    "category_action": "fa-crosshairs",
    "category_multiplayer": "fa-users",
    "category_arcade": "fa-flag-checkered",
    "category_learning": "fa-graduation-cap",
    "category_strategy": "fa-chess",
    "category_dev_tools": "fa-tools",
}


def upgrade():
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.add_column(sa.Column('icon', sa.String(length=50), nullable=True))

    tag = sa.table("tag", sa.column("name", sa.String), sa.column("icon", sa.String))
    for name, icon in CATEGORY_ICONS.items():
        # Only where an editor hasn't chosen one, which can't have happened yet, but keeps this safe to rerun
        op.execute(tag.update().where(tag.c.name == name, tag.c.icon.is_(None)).values(icon=icon))


def downgrade():
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.drop_column('icon')
