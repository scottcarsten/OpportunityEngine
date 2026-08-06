"""Protect decided generated documents.

Mirrors `database/schema.sql`'s `protect_generated_document_update`/
`_delete` triggers, closing the gap `OE-ADR-020`/`OE-ADR-023` flagged:
`generated_documents` was the one append-only-relevant table with no
protective trigger. Once a document is `approved` or `rejected`, it can
never be updated again; rows are never deleted.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER protect_generated_document_update
        BEFORE UPDATE ON generated_documents
        WHEN OLD.status IN ('approved', 'rejected')
        BEGIN
            SELECT RAISE(ABORT, 'Decided documents are immutable.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_generated_document_delete
        BEFORE DELETE ON generated_documents
        BEGIN
            SELECT RAISE(ABORT, 'Generated documents are append-only.');
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER protect_generated_document_update")
    op.execute("DROP TRIGGER protect_generated_document_delete")
