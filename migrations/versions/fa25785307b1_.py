"""Add dashboards, and seed the homepage dashboard

Revision ID: fa25785307b1
Revises: e7c3a1f5b2d8
Create Date: 2026-11-19 19:59:36.885790

"""
from alembic import op
import sqlalchemy as sa
import datetime

# revision identifiers, used by Alembic.
revision = 'fa25785307b1'
down_revision = 'e7c3a1f5b2d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dashboard',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('dashboard_widget',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dashboard_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=True),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('query_string', sa.String(length=512), nullable=True),
    sa.Column('limit', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['dashboard_id'], ['dashboard.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    seed_homepage()


def seed_homepage():
    """
    Insert the homepage layout from before dashboards existed as dashboard 1.
    Uses table stubs rather than the models, so it doesn't break when the models change.
    """
    now = datetime.datetime.utcnow()

    dashboard = sa.table('dashboard',
        sa.column('id', sa.Integer),
        sa.column('title', sa.String),
        sa.column('created_at', sa.DateTime))

    widget = sa.table('dashboard_widget',
        sa.column('dashboard_id', sa.Integer),
        sa.column('type', sa.String),
        sa.column('title', sa.String),
        sa.column('order', sa.Integer),
        sa.column('created_at', sa.DateTime),
        sa.column('query_string', sa.String),
        sa.column('limit', sa.Integer))

    op.bulk_insert(dashboard, [
        {'id': 1, 'title': 'Home', 'created_at': now},
    ])

    # (type, title, query_string, limit)
    widgets = [
        ('SPOTLIGHT', None, None, 6),
        ('ROW', 'Recently Added', 'sort=approved_at&order=desc', 4),
        ('ROW', 'Recently Updated', 'sort=last_release&order=desc', 4),
        ('ROW', 'Top Games', 'type=game&sort=score&order=desc', 8),
        ('ROW', 'Top Mods', 'type=mod&sort=score&order=desc', 8),
        ('ROW', 'Top Texture Packs', 'type=txp&sort=score&order=desc', 8),
        ('TAGS', 'Search by Tags', None, None),
        ('ROW', 'Highest Reviewed', 'sort=reviews&order=desc', 4),
        ('REVIEWS', 'Recent Positive Reviews', None, 5),
    ]

    op.bulk_insert(widget, [
        {
            'dashboard_id': 1,
            'type': type_,
            'title': title,
            'order': i,
            'created_at': now,
            'query_string': query_string,
            'limit': limit,
        } for i, (type_, title, query_string, limit) in enumerate(widgets)
    ])

    # The id was set explicitly, so move the sequence past it
    op.execute("SELECT setval('dashboard_id_seq', (SELECT MAX(id) FROM dashboard))")


def downgrade():
    op.drop_table('dashboard_widget')
    op.drop_table('dashboard')
