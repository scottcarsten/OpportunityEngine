"""Shared test fixtures.

Two independent leaks can put real `.env` values (e.g. a working
Telegram bot token) into a test run:

1. `Settings` reads `.env` directly via pydantic-settings' own
   `env_file` config, whenever a test doesn't pass explicit overrides.
2. `backend.app` has a *module-level* `app = create_app()` line, which
   unconditionally calls `load_dotenv()` and mutates the real process
   `os.environ` - this persists for the rest of the pytest process.

Both must be disabled before test collection even begins - by the time
any fixture (even session-scoped) runs, `backend.app` has already been
imported (its module-level code already executed) by whichever test
file happened to import it first. `pytest_configure` is the one hook
that fires before collection starts, so it's the only place early
enough to actually prevent this.
"""

from pydantic_settings import SettingsConfigDict


def pytest_configure() -> None:
    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: None

    from backend.config import Settings, get_settings

    Settings.model_config = SettingsConfigDict(
        env_file=None, env_prefix="OPPORTUNITY_ENGINE_", extra="ignore"
    )
    get_settings.cache_clear()
