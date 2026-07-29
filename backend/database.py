"""SQLite initialization and connection management."""

import sqlite3
from pathlib import Path


class Database:
    """Own the local SQLite database lifecycle."""

    def __init__(self, database_path: Path, schema_path: Path) -> None:
        self.database_path = database_path
        self.schema_path = schema_path
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("database has not been initialized")
        return self._connection

    def initialize(self) -> None:
        """Create the database, apply the baseline schema, and verify access."""
        if not self.schema_path.is_file():
            raise RuntimeError(f"database schema not found: {self.schema_path}")

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        # FastAPI runs synchronous endpoints in worker threads. The connection
        # is application-owned and may therefore be used outside the lifespan
        # thread; transactions remain short and service-controlled.
        connection = sqlite3.connect(self.database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")

        existing_version = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_versions'"
        ).fetchone()
        if existing_version is None:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))

        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
        if foreign_keys is None or foreign_keys[0] != 1:
            connection.close()
            raise RuntimeError("SQLite foreign-key enforcement is disabled")

        self._connection = connection

    def ping(self) -> bool:
        """Return whether the database responds to a minimal query."""
        return self.connection.execute("SELECT 1").fetchone()[0] == 1

    def close(self) -> None:
        """Close the active connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
