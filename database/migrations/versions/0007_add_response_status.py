"""Add opportunities.response_status for tracking employer-response outcomes.

Deferred explicitly by `OE-ADR-034` ("outcome/response tracking... a
bigger, separate feature if wanted later") - this is that feature. New
nullable column with a CHECK constraint, independent of both
`lifecycle_status` and `applied_at` by the same design principle: it
doesn't hide or replace either. Unlike `0005`/`0004`'s plain
`op.add_column`, SQLite can't add a CHECK constraint via bare ALTER
TABLE, so this uses `batch_alter_table` (table recreation) - same
mechanism `0003` used for `notifications.channel`. No triggers exist on
`opportunities` (confirmed by inspection), so unlike `0003` nothing
needs dropping/recreating around the batch op. The value is `declined`,
not `rejected` - `lifecycle_status` already has a `rejected` meaning
Scott rejected the opportunity during triage; reusing the same word for
"the employer rejected you" would collide in every status-filter query
that dispatches on the raw string. See `OE-ADR-041`.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RESPONSE_STATUS_CHECK = (
    "response_status IS NULL OR response_status IN "
    "('responded', 'interview', 'offer', 'declined', 'withdrawn')"
)


def upgrade() -> None:
    with op.batch_alter_table("opportunities", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("response_status", sa.Text()))
        batch_op.create_check_constraint(
            "ck_opportunities_response_status", _RESPONSE_STATUS_CHECK
        )
    op.create_index(
        "idx_opportunities_response_status", "opportunities", ["response_status"]
    )


def downgrade() -> None:
    op.drop_index("idx_opportunities_response_status", table_name="opportunities")
    with op.batch_alter_table("opportunities", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_opportunities_response_status", type_="check")
        batch_op.drop_column("response_status")
