"""Restrict the resolution tags to texture packs

The resolution tags only make sense for texture packs. Each is removed from packages of other types, with an audit log
entry on each package, as Tag.applies_to would otherwise make their next edit fail.

Revision ID: a9d3f1c7e5b2
Revises: f2b6d8e4a1c9
Create Date: 2026-11-22 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a9d3f1c7e5b2'
down_revision = 'f2b6d8e4a1c9'
branch_labels = None
depends_on = None


# Tag name: the package types it can be given to
RESTRICTIONS = {
    # Texture resolutions
    "less_than_px": ["TXP"],
    "16px": ["TXP"],
    "32px": ["TXP"],
    "64px": ["TXP"],
    "128px": ["TXP"],
}


def upgrade():
    names = list(RESTRICTIONS.keys())
    names_param = sa.bindparam("names", names, type_=postgresql.ARRAY(sa.String))

    for name, package_types in RESTRICTIONS.items():
        op.execute(sa.text("UPDATE tag SET package_types = CAST(:types AS packagetype[]) WHERE name = :name")
                .bindparams(types=package_types, name=name))

    # One audit log entry per package that loses tags, by the system user, before they're removed
    op.execute(sa.text("""
        INSERT INTO audit_log_entry (created_at, causer_id, severity, title, url, package_id, description)
        SELECT
            timezone('utc', now()),
            (SELECT id FROM "user" WHERE username = 'ContentDB'),
            'EDITOR',
            left('Removed tags from ' || p.title || ': ' || string_agg(t.title, ', ' ORDER BY t.title), 100),
            '/packages/' || u.username || '/' || p.name || '/',
            p.id,
            'These tags can now only be used on other types of package.'
        FROM tags pt
        JOIN tag t ON t.id = pt.tag_id
        JOIN package p ON p.id = pt.package_id
        JOIN "user" u ON u.id = p.author_id
        WHERE t.name = ANY(:names) AND NOT (p.type = ANY(t.package_types))
        GROUP BY p.id, p.title, p.name, u.username
    """).bindparams(names_param))

    op.execute(sa.text("""
        DELETE FROM tags pt
        USING tag t, package p
        WHERE t.id = pt.tag_id AND p.id = pt.package_id
            AND t.name = ANY(:names) AND NOT (p.type = ANY(t.package_types))
    """).bindparams(names_param))


def downgrade():
    # The removed tags aren't added back, but the audit log entries say which packages had them
    op.execute(sa.text("UPDATE tag SET package_types = '{}' WHERE name = ANY(:names)")
            .bindparams(sa.bindparam("names", list(RESTRICTIONS.keys()), type_=postgresql.ARRAY(sa.String))))
