"""Allow 'telegram' as a notifications.channel value.

ntfy's free public server proved unreliable for iOS remote push in real
live testing (OE-ADR-035) - Telegram replaces it as the push channel.
'ntfy' stays in the enum as a harmless historical value, same as
'local'/'other' already being unused; no reason to churn the schema
further to remove it. Same batch-recreate-plus-trigger-restore shape as
`0003`.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
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
            "channel IN ('local', 'dashboard', 'email', 'sms', 'ntfy', 'telegram', 'other')",
        )
    op.execute(_TRIGGER_SQL)


def downgrade() -> None:
    op.execute("DROP TRIGGER require_approval_for_external_notification_insert")
    with op.batch_alter_table("notifications", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_notifications_channel", type_="check")
        batch_op.create_check_constraint(
            "ck_notifications_channel",
            "channel IN ('local', 'dashboard', 'email', 'sms', 'ntfy', 'other')",
        )
    op.execute(_TRIGGER_SQL)
