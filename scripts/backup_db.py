#!/usr/bin/env python3
"""Safely snapshot the OpportunityEngine SQLite database (OE-ADR-040).

Stdlib only, no imports from backend/ - deliberately runs without the
project's venv, same reasoning as OE-ADR-039's curl-not-Python alert
unit: a backup should still work even if the app's own venv is broken.

Uses sqlite3.Connection.backup(), the stdlib wrapper around SQLite's
online backup API - safe to run against a live database in WAL mode,
unlike a raw file copy which could grab an inconsistent mid-write
state. Then runs PRAGMA integrity_check against the snapshot and exits
non-zero if it doesn't come back clean, so corruption is caught at
backup time rather than months later when the backup is actually needed.

Usage: python3 backup_db.py <source.db> <destination.db>
"""

import sqlite3
import sys


def backup_database(source_path: str, dest_path: str) -> None:
    source = sqlite3.connect(source_path)
    dest = sqlite3.connect(dest_path)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()

    check = sqlite3.connect(dest_path)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()

    if result != "ok":
        print(f"Integrity check failed on backup: {result}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: backup_db.py <source.db> <destination.db>", file=sys.stderr)
        sys.exit(2)
    backup_database(sys.argv[1], sys.argv[2])
    print("Backup and integrity check succeeded.")
