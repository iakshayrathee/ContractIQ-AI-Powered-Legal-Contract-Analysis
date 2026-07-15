import logging
import ssl
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _prepare_asyncpg_url(raw_url: str) -> tuple[str, dict]:
    """
    Strip sslmode from the query string (asyncpg doesn't understand it)
    and return the cleaned URL plus connect_args for SSL.
    """
    parsed = urlparse(raw_url)
    query = parse_qs(parsed.query)

    sslmode = query.pop("sslmode", [None])[0]

    # Rebuild URL without sslmode so asyncpg never sees it
    new_query = urlencode(query, doseq=True)
    cleaned = urlunparse(parsed._replace(query=new_query))

    connect_args: dict = {}
    if sslmode in ("require", "prefer", "verify-ca", "verify-full"):
        context = ssl.create_default_context()
        if sslmode == "require":
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = context

    return cleaned, connect_args


async def init_db(settings: Settings) -> None:
    """Create the async engine, session factory, and run table creation."""
    global _engine, _session_factory

    db_url, connect_args = _prepare_asyncpg_url(settings.database_url)

    _engine = create_async_engine(
        db_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        connect_args=connect_args,
    )
    
    # Enable SQLite foreign key support for cascade deletes if SQLite is used
    if "sqlite" in db_url:
        from sqlalchemy import event
        @event.listens_for(_engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    logger.info("Database initialised: %s", db_url.split("@")[-1])


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection closed.")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _session_factory
