"""CLI entry point for repeatable, manually-triggered collection jobs.

Per `OE-ADR-010`, jobs are exposed through application services plus a CLI
command; cron/systemd scheduling is deliberately not wired up yet.
"""

import argparse
import sys

from backend.adapters.himalayas import HimalayasAdapter
from backend.adapters.jobspresso import JobspressoAdapter
from backend.adapters.remotive import RemotiveAdapter
from backend.adapters.we_work_remotely import WeWorkRemotelyAdapter
from backend.config import get_settings
from backend.database import Database
from backend.services.collection_service import CollectionService
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService

ADAPTERS = {
    "we_work_remotely": WeWorkRemotelyAdapter,
    "himalayas": HimalayasAdapter,
    "remotive": RemotiveAdapter,
    "jobspresso": JobspressoAdapter,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Run one source adapter.")
    collect_parser.add_argument("source", choices=sorted(ADAPTERS))

    args = parser.parse_args(argv)

    settings = get_settings()
    constitution = load_constitution(settings.constitution_path)
    database = Database(database_path=settings.database_path)
    database.initialize()
    try:
        adapter = ADAPTERS[args.source]()
        service = CollectionService(database, constitution)
        result = service.run(adapter)
        # Runs after every collection, not just this source's — expiration
        # only depends on expires_at having passed, not on which source was
        # just refreshed, so it's always safe to sweep table-wide (OE-ADR-028).
        opportunity_service = OpportunityService(database, constitution)
        expired_ids = opportunity_service.expire_stale_opportunities()
        result["expired_count"] = len(expired_ids)
        # Same table-wide, collection-triggered pattern as expiration above -
        # a due reminder doesn't depend on which source was just refreshed
        # (OE-ADR-030).
        reminder_ids = opportunity_service.surface_due_reminders()
        result["reminders_sent"] = len(reminder_ids)
    finally:
        database.close()

    print(result)
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
