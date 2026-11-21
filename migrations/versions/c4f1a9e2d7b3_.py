"""Add game category tags

Revision ID: c4f1a9e2d7b3
Revises: b8e4d2a61f07
Create Date: 2026-11-21 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'c4f1a9e2d7b3'
down_revision = 'b8e4d2a61f07'
branch_labels = None
depends_on = None


# Prefixed, as several plain names (survival, creative, puzzle, multiplayer, ...) are already mod tags.
# Kept to 20 characters, the limit of the name field in the tag editor.
CATEGORIES = [
    ("category_survival", "Survival Sandbox",
        "Gather resources, craft tools, and survive in an open world."),
    ("category_creative", "Creative & Building",
        "Build freely, with unlimited resources or a focus on construction."),
    ("category_adventure", "Adventure & RPG",
        "Explore, follow a story, complete quests, and level up."),
    ("category_puzzle", "Puzzle",
        "Solve puzzles and challenges that need thinking rather than quick reflexes."),
    ("category_action", "Action & Combat",
        "Fight monsters or other players, with weapons, magic, or guns."),
    ("category_multiplayer", "Multiplayer & Party",
        "Made to be played with others, such as minigames and party games."),
    ("category_arcade", "Arcade & Racing",
        "Short, fast-paced games, such as racing, platformers, and classic arcade games."),
    ("category_learning", "Learning",
        "Learn a skill or subject while you play, such as programming, electronics, maths, or languages."),
    ("category_strategy", "Strategy & Simulation",
        "Plan and manage, such as running a city, a farm, or a business, or commanding an army."),
    ("category_dev_tools", "Developer Tools",
        "Tools for developers, such as editors and game bases."),
]


tag = sa.table(
    "tag",
    sa.column("name", sa.String),
    sa.column("title", sa.String),
    sa.column("description", sa.String),
    sa.column("backgroundColor", sa.String),
    sa.column("textColor", sa.String),
    sa.column("views", sa.Integer),
    sa.column("kind", postgresql.ENUM(name="tagkind", create_type=False)),
    sa.column("package_types", postgresql.ARRAY(postgresql.ENUM(name="packagetype", create_type=False))),
)


def upgrade():
    rows = [{
        "name": name,
        "title": title,
        "description": description,
        "backgroundColor": "000000",
        "textColor": "ffffff",
        "views": 0,
        "kind": "CATEGORY",
        "package_types": ["GAME"],
    } for name, title, description in CATEGORIES]

    # An instance may have created some of these by hand already
    op.execute(postgresql.insert(tag).values(rows).on_conflict_do_nothing(index_elements=["name"]))


def downgrade():
    names = [name for name, _, _ in CATEGORIES]
    op.execute(sa.text("DELETE FROM tags WHERE tag_id IN (SELECT id FROM tag WHERE name = ANY(:names))")
            .bindparams(sa.bindparam("names", names, type_=postgresql.ARRAY(sa.String))))
    op.execute(sa.text("DELETE FROM tag WHERE name = ANY(:names)")
            .bindparams(sa.bindparam("names", names, type_=postgresql.ARRAY(sa.String))))
