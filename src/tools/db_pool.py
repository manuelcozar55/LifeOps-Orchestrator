"""
Shared Postgres Connection Pool
================================
Single source of truth for the Supabase connection pool.

Both the LangGraph PostgresSaver (checkpointing / HIL) and the DatabaseManager
(token telemetry) use this shared pool, eliminating the duplicate pool that
previously doubled the connection count against Supabase.

Resilience strategy (against Supabase PgBouncer idle-disconnect):
  - check=ConnectionPool.check_connection  → validates every connection before use
  - max_idle=60                            → closes connections before PgBouncer does (~60s)
  - reconnect_timeout=300                  → auto-reconnects for up to 5 minutes on outage
  - TCP keepalives (keepalives_idle=30s)   → OS-level heartbeat prevents silent drops
  - sslmode=require                        → explicit TLS negotiation with Supabase

Usage:
    from src.tools.db_pool import get_shared_pool
    pool = get_shared_pool()
"""
import os
import structlog
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from psycopg_pool import ConnectionPool

logger = structlog.get_logger()

_pool: ConnectionPool | None = None


def get_shared_pool() -> ConnectionPool:
    """Returns the application-wide ConnectionPool, creating it on first call.

    Raises ValueError if SUPABASE_DB_URL is missing or still holds the
    placeholder value from .env.example — this fails fast at startup rather
    than producing cryptic errors later.
    """
    global _pool
    if _pool is not None:
        return _pool

    db_url = os.getenv("SUPABASE_DB_URL", "")
    if not db_url or db_url.startswith("postgresql://postgres.xxx"):
        raise ValueError(
            "SUPABASE_DB_URL no está configurada o contiene el valor placeholder. "
            "Revisa tu archivo .env."
        )

    # Enrich the connection URL with SSL + TCP keepalive parameters.
    # This prevents "SSL error: unexpected eof while reading" caused by
    # Supabase PgBouncer silently dropping idle connections server-side.
    parsed = urlparse(db_url)
    params = parse_qs(parsed.query)
    params.setdefault("sslmode", ["require"])
    params.setdefault("keepalives", ["1"])
    params.setdefault("keepalives_idle", ["30"])
    params.setdefault("keepalives_interval", ["10"])
    params.setdefault("keepalives_count", ["3"])
    db_url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

    logger.info("Initialising shared Postgres connection pool (resilient config)")
    _pool = ConnectionPool(
        conninfo=db_url,
        min_size=2,
        max_size=10,
        max_idle=60,                           # below Supabase PgBouncer ~60s idle timeout
        timeout=30,
        reconnect_timeout=300,                 # auto-reconnect for up to 5 min on outage
        check=ConnectionPool.check_connection, # validate connection alive before each use
        kwargs={"autocommit": True},
    )
    logger.info(
        "Pool ready",
        max_idle=60,
        check="check_connection",
        reconnect_timeout=300,
        keepalives_idle=30,
    )
    return _pool
