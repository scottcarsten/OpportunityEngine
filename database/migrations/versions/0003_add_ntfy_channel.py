"""Allow 'ntfy' as a notifications.channel value.

Adds the push-notification channel for OE-ADR-029. SQLite can't alter a
CHECK constraint in place, and Alembic's batch-recreate doesn't preserve
triggers, so the existing
`require_approval_for_external_notification_insert` trigger is dropped
before the batch operation and recreated verbatim afterward.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGER_SQL = """
CREATE TRIGGER require_approval_for_external_notification_insert
BEFORE INSERT ON notifications
WHEN NEW.is_external = 1
BEGIN
    SELECT CASE
        WHEN NEW.approval_request_id IS NULL
        THEN RAISE(ABORT, 'External notifications require an approval request.')
        WHEN NOT EXISTS (
            SELECT 1
            FROM approval_requests
            WHERE id = NEW.approval_request_id
              AND status = 'approved'
              AND action_type IN ('email', 'external_message')
              AND (expires_at IS NULL OR expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        THEN RAISE(ABORT, 'External notification approval is missing, invalid, or expired.')
    END;
END;
"""


def upgrade() -> None:
    op.execute("DROP TRIGGER require_approval_for_external_notification_insert")
    with op.batch_alter_table("notifications", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_notifications_channel", type_="check")
        batch_op.create_check_constraint(
            "ck_notifications_channel",
            "channel IN ('local', 'dashboard', 'email', 'sms', 'ntfy', 'other')",
        )
    op.execute(_TRIGGER_SQL)


def downgrade() -> None:
    op.execute("DROP TRIGGER require_approval_for_external_notification_insert")
    with op.batch_alter_table("notifications", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_notifications_channel", type_="check")
        batch_op.create_check_constraint(
            "ck_notifications_channel",
            "channel IN ('local', 'dashboard', 'email', 'sms', 'other')",
        )
    op.execute(_TRIGGER_SQL)
