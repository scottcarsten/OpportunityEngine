"""Add opportunities.remind_at for follow-up reminders.

Plain nullable column add (no CHECK constraint involved, unlike `0003`)
plus a composite index for `OpportunityService.surface_due_reminders()`'s
`lifecycle_status = 'deferred' AND remind_at < now` sweep. See
`OE-ADR-030`.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("remind_at", sa.Text()))
    op.create_index(
        "idx_opportunities_status_remind", "opportunities", ["lifecycle_status", "remind_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_opportunities_status_remind", table_name="opportunities")
    op.drop_column("opportunities", "remind_at")
