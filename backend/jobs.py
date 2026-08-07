"""Shared collect-and-sweep job, run by both the CLI and the Telegram listener."""

from backend.adapters.base import SourceAdapter
from backend.database import Database
from backend.services.approval_service import ApprovalService
from backend.services.collection_service import CollectionService
from backend.services.constitution_service import Constitution
from backend.services.opportunity_service import OpportunityService


def run_collection(database: Database, constitution: Constitution, adapter: SourceAdapter) -> dict:
    """Run one source adapter, then every table-wide sweep that follows it.

    Expiration, reminders, and approval-expiry don't depend on which
    source was just refreshed (OE-ADR-028/030/032), so they always run
    together with collection, regardless of caller.
    """
    result = CollectionService(database, constitution).run(adapter)

    opportunity_service = OpportunityService(database, constitution)
    expired_ids = opportunity_service.expire_stale_opportunities()
    result["expired_count"] = len(expired_ids)

    reminder_ids = opportunity_service.surface_due_reminders()
    result["reminders_sent"] = len(reminder_ids)

    expired_approval_ids = ApprovalService(database, constitution).expire_stale_requests()
    result["expired_approvals_count"] = len(expired_approval_ids)

    return result
