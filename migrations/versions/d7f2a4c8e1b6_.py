"""Replace the license and media license with a list of licenses

Downgrading keeps only the first license by name, for both the code and media. Packages with no licenses get
the license with the lowest id.

Revision ID: d7f2a4c8e1b6
Revises: b3e7a9c1d5f8
Create Date: 2026-11-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7f2a4c8e1b6'
down_revision = 'b3e7a9c1d5f8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('package_license',
        sa.Column('package_id', sa.Integer(), nullable=False),
        sa.Column('license_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['license_id'], ['license.id']),
        sa.ForeignKeyConstraint(['package_id'], ['package.id']),
        sa.PrimaryKeyConstraint('package_id', 'license_id'))

    op.execute("""
        INSERT INTO package_license (package_id, license_id)
        SELECT id, license_id FROM package
        UNION
        SELECT id, media_license_id FROM package
    """)

    op.drop_constraint('ck_license_txp', 'package', type_='check')
    op.drop_column('package', 'license_id')
    op.drop_column('package', 'media_license_id')


def downgrade():
    op.add_column('package', sa.Column('license_id', sa.Integer(), nullable=True))
    op.add_column('package', sa.Column('media_license_id', sa.Integer(), nullable=True))

    op.execute("""
        UPDATE package SET license_id = COALESCE((
            SELECT l.id FROM package_license pl JOIN license l ON l.id = pl.license_id
            WHERE pl.package_id = package.id ORDER BY lower(l.name), l.id LIMIT 1),
            (SELECT min(id) FROM license))
    """)
    op.execute("UPDATE package SET media_license_id = license_id")

    op.alter_column('package', 'license_id', nullable=False)
    op.alter_column('package', 'media_license_id', nullable=False)
    op.create_foreign_key('package_license_id_fkey', 'package', 'license', ['license_id'], ['id'])
    op.create_foreign_key('package_media_license_id_fkey', 'package', 'license', ['media_license_id'], ['id'])
    op.create_check_constraint('ck_license_txp', 'package', "type != 'TXP' OR license_id = media_license_id")

    op.drop_table('package_license')
