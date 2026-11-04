"""Store email_subscription emails as a sha256 hash

Revision ID: b7d4f1e9a2c6
Revises: b4e8d2a6c1f3
Create Date: 2026-11-04 14:00:00.000000

"""
import hashlib

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b7d4f1e9a2c6'
down_revision = 'b4e8d2a6c1f3'
branch_labels = None
depends_on = None


def hash_email(email: str) -> str:
	# Copy of app.models.users.hash_email, as migrations shouldn't depend on app code
	return hashlib.sha256(email.lower().encode("utf-8")).hexdigest()


def upgrade():
	conn = op.get_bind()

	op.add_column("email_subscription", sa.Column("email_hash", sa.String(length=64), nullable=True))

	# Hash in Python rather than SQL so the values are guaranteed to match hash_email. Addresses with the same hash
	# are merged, keeping the oldest. The address stays blacklisted if any of them were.
	rows = conn.execute(sa.text("SELECT id, email, blacklisted FROM email_subscription ORDER BY id")).fetchall()
	keep = {}
	to_delete = []
	for id, email, blacklisted in rows:
		email_hash = hash_email(email)
		if email_hash in keep:
			keep[email_hash]["blacklisted"] = keep[email_hash]["blacklisted"] or blacklisted
			to_delete.append(id)
		else:
			keep[email_hash] = {"id": id, "email_hash": email_hash, "blacklisted": blacklisted}

	if to_delete:
		conn.execute(sa.text("DELETE FROM email_subscription WHERE id = ANY(:ids)"), {"ids": to_delete})

	if keep:
		conn.execute(sa.text("UPDATE email_subscription SET email_hash = :email_hash, blacklisted = :blacklisted "
				"WHERE id = :id"), list(keep.values()))

	op.alter_column("email_subscription", "email_hash", nullable=False)
	op.create_unique_constraint("email_subscription_email_hash_key", "email_subscription", ["email_hash"])
	op.drop_column("email_subscription", "email")


def downgrade():
	# Downgrading would need the plaintext emails, which no longer exist. Restoring only the ones that match a user
	# would silently drop the blacklist for everyone else.
	raise Exception("Cannot downgrade: email_subscription only contains hashes, the original emails are gone")
