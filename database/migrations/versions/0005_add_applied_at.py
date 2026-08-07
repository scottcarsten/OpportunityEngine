"""Add opportunities.applied_at for tracking real-world applications.

Plain nullable column add (identical shape to `0004`'s `remind_at`).
`applied_at` is independent of `lifecycle_status` by design - marking
something applied doesn't change what stage it's at in the review
pipeline. See `OE-ADR-034`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("applied_at", sa.Text()))
    op.create_index("idx_opportunities_applied_at", "opportunities", ["applied_at"])


def downgrade() -> None:
    op.drop_index("idx_opportunities_applied_at", table_name="opportunities")
    op.drop_column("opportunities", "applied_at")
