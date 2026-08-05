"""CLI entry point for repeatable, manually-triggered collection jobs.

Per `OE-ADR-010`, jobs are exposed through application services plus a CLI
command; cron/systemd scheduling is deliberately not wired up yet.
"""

import argparse
import sys

from backend.adapters.we_work_remotely import WeWorkRemotelyAdapter
from backend.config import get_settings
from backend.database import Database
from backend.services.collection_service import CollectionService
from backend.services.constitution_service import load_constitution

ADAPTERS = {
    "we_work_remotely": WeWorkRemotelyAdapter,
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
    finally:
        database.close()

    print(result)
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
