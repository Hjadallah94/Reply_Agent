"""add order confirmation status

Revision ID: d0ec71e17256
Revises: 9e7e58d38a35
Create Date: 2026-09-01 18:33:00.021484

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd0ec71e17256'
down_revision: str | None = '9e7e58d38a35'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


order_confirmation_status_enum = sa.Enum(
    "pending", "confirmed", "declined", "escalated", name="order_confirmation_status"
)


def upgrade() -> None:
    # Unlike op.create_table(), op.add_column() does NOT implicitly create the enum type first
    # — must do it explicitly, or the ALTER TABLE fails with "type ... does not exist" (found
    # live running this migration's own round-trip check).
    order_confirmation_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "orders", sa.Column("confirmation_status", order_confirmation_status_enum, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("orders", "confirmation_status")
    # add_column's inline sa.Enum(...) creates a Postgres ENUM type that drop_column does NOT
    # implicitly drop — must do it explicitly (recurring gotcha, see every prior migration this
    # session that added an enum column).
    order_confirmation_status_enum.drop(op.get_bind(), checkfirst=True)
