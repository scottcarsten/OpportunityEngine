"""SQLAlchemy engine, migrations, and session lifecycle."""

from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


_ALEMBIC_INI_PATH = Path("alembic.ini")


class Database:
    """Own the local SQLite database lifecycle via SQLAlchemy and Alembic."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None
        self._lock = RLock()

    def initialize(self) -> None:
        """Create the database, apply migrations, and verify access."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # FastAPI runs synchronous endpoints in worker threads. StaticPool plus
        # check_same_thread=False keeps one shared DBAPI connection for the
        # application's lifetime, matching the previous single-connection
        # model; the RLock in `session()` still serializes access to it.
        engine = create_engine(
            f"sqlite:///{self.database_path}",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.close()

        self._engine = engine
        self._run_migrations()
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

        with self.session() as session:
            foreign_keys = session.execute(text("PRAGMA foreign_keys")).scalar()
        if foreign_keys != 1:
            self.close()
            raise RuntimeError("SQLite foreign-key enforcement is disabled")

    def _run_migrations(self) -> None:
        config = Config(str(_ALEMBIC_INI_PATH))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.database_path}")
        command.upgrade(config, "head")

    def ping(self) -> bool:
        """Return whether the database responds to a minimal query."""
        with self.session() as session:
            return session.execute(text("SELECT 1")).scalar() == 1

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("database has not been initialized")
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Serialize access to a session bound to the application-owned engine."""
        if self._session_factory is None:
            raise RuntimeError("database has not been initialized")
        with self._lock:
            session = self._session_factory()
            try:
                yield session
            finally:
                session.close()

    def close(self) -> None:
        """Dispose the engine and its underlying connection."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
