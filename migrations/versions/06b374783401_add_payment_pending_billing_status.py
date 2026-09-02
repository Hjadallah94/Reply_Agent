"""add payment_pending billing status

Revision ID: 06b374783401
Revises: 45069662641c
Create Date: 2026-09-02 16:46:51.590589

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06b374783401"
down_revision: str | None = "45069662641c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic's autogenerate doesn't detect enum-value additions (only structural table/column
    # changes) — hand-written. Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction
    # as long as the new value isn't used in the same transaction, which it isn't here.
    op.execute("ALTER TYPE billing_status ADD VALUE 'payment_pending'")


def downgrade() -> None:
    # Postgres has no direct "DROP VALUE" for an enum — the standard workaround is to swap the
    # column to text, recreate the type without the value, then swap back. This fails (by
    # design) if any row still holds 'payment_pending' at downgrade time — same limitation any
    # real downgrade of a removed enum value has; no attempt to silently coerce that data.
    op.execute("ALTER TABLE subscriptions ALTER COLUMN billing_status TYPE text")
    op.execute("ALTER TYPE billing_status RENAME TO billing_status_old")
    op.execute("CREATE TYPE billing_status AS ENUM ('trialing', 'active', 'past_due', 'canceled')")
    op.execute(
        "ALTER TABLE subscriptions ALTER COLUMN billing_status "
        "TYPE billing_status USING billing_status::billing_status"
    )
    op.execute("DROP TYPE billing_status_old")
