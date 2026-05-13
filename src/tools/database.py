"""
LifeOps Database Manager
========================
Handles token usage recording and stats queries via Supabase (Postgres).

Uses the application-wide shared ConnectionPool from src.tools.db_pool
instead of creating its own pool, eliminating the duplicate connection
overhead that previously doubled the connection count against Supabase.

Resilience: all DB operations use _with_retry() (2 retries, 0.5s backoff)
to survive transient mid-query failures that slip past check_connection.

Schema migrations: _init_schema runs CREATE TABLE IF NOT EXISTS + ALTER TABLE
ADD COLUMN IF NOT EXISTS for each column, so it is safe to run on an existing
table that was created with an older schema version.

Daily token limit: DAILY_TOKEN_LIMIT (default 100 000, overridable via
LIFEOPS_DAILY_TOKEN_LIMIT env var).  check_daily_budget() is checked before
each graph invocation to enforce a hard cap.
"""
import os
import time
import structlog
from typing import Dict, Any, Tuple
from psycopg import OperationalError
from langsmith import traceable

from src.tools.db_pool import get_shared_pool

logger = structlog.get_logger()

# Daily token hard cap — override via env var (tokens, not cost)
DAILY_TOKEN_LIMIT: int = int(os.getenv("LIFEOPS_DAILY_TOKEN_LIMIT", "100000"))


class DatabaseManager:
    """Singleton-pattern manager for token usage persistence."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._ready = False
            cls._instance._init_schema()
        return cls._instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _with_retry(self, fn, max_retries: int = 2, backoff: float = 0.5):
        """Execute fn(pool) with retry on transient Postgres OperationalErrors."""
        pool = get_shared_pool()
        for attempt in range(max_retries + 1):
            try:
                return fn(pool)
            except OperationalError as e:
                if attempt < max_retries:
                    logger.warning(
                        "DB transient error, retrying",
                        attempt=attempt + 1,
                        max=max_retries,
                        error=str(e),
                    )
                    time.sleep(backoff * (attempt + 1))
                else:
                    raise

    def _init_schema(self):
        """Ensures token_usage table and all columns exist.

        Uses CREATE TABLE IF NOT EXISTS + ALTER TABLE ADD COLUMN IF NOT EXISTS
        so it is idempotent and safe on pre-existing tables with older schemas.
        """
        create_sql = """
        CREATE TABLE IF NOT EXISTS token_usage (
            id            SERIAL PRIMARY KEY,
            chat_id       TEXT         NOT NULL,
            input_tokens  INTEGER      DEFAULT 0,
            output_tokens INTEGER      DEFAULT 0,
            total_tokens  INTEGER      DEFAULT 0,
            created_at    TIMESTAMPTZ  DEFAULT NOW()
        );
        """
        # Migration stmts: add columns that may be missing from older schema versions.
        # ADD COLUMN IF NOT EXISTS is safe to run even when the column already exists.
        migrations = [
            "ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS total_tokens  INTEGER     DEFAULT 0;",
            "ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ DEFAULT NOW();",
            # Legacy alias: some deployments had 'timestamp' instead of 'created_at'.
            # We keep 'created_at' as canonical; if the old column exists it stays
            # and will be ignored by our queries.
        ]

        try:
            def _do(pool):
                with pool.connection() as conn:
                    conn.execute(create_sql)
                    for stmt in migrations:
                        conn.execute(stmt)

            self._with_retry(_do)
            self._ready = True
            logger.info("DatabaseManager: token_usage schema ready (shared pool).")
        except Exception as e:
            logger.error("DatabaseManager: schema init failed", error=str(e))
            self._ready = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @traceable(run_type="tool", name="db_record_usage")
    def record_usage(self, chat_id: str, input_t: int, output_t: int) -> None:
        """Persists LLM token usage including the cumulative total per row."""
        if not self._ready:
            self._init_schema()
        if not self._ready:
            return

        total_t = input_t + output_t
        sql = (
            "INSERT INTO token_usage (chat_id, input_tokens, output_tokens, total_tokens) "
            "VALUES (%s, %s, %s, %s);"
        )

        def _do(pool):
            with pool.connection() as conn:
                conn.execute(sql, (chat_id, input_t, output_t, total_t))

        try:
            self._with_retry(_do)
            logger.info(
                "Usage recorded",
                chat_id=chat_id,
                in_t=input_t,
                out_t=output_t,
                total_t=total_t,
            )
        except Exception as e:
            logger.error("Failed to record usage after retries", error=str(e))

    def check_daily_budget(self, chat_id: str) -> Tuple[bool, int, int]:
        """Returns (over_limit, tokens_used_today, daily_limit).

        over_limit=True means the budget is exhausted for today.
        Falls back to (False, 0, DAILY_TOKEN_LIMIT) on any DB error so the
        system stays operational rather than silently blocking all requests.
        """
        sql = (
            "SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage "
            "WHERE chat_id = %s AND created_at >= CURRENT_DATE;"
        )

        def _do(pool):
            with pool.connection() as conn:
                row = conn.execute(sql, (chat_id,)).fetchone()
                return int(row[0]) if row else 0

        try:
            used = self._with_retry(_do)
            over = used >= DAILY_TOKEN_LIMIT
            return over, used, DAILY_TOKEN_LIMIT
        except Exception as e:
            logger.warning("check_daily_budget failed, allowing request", error=str(e))
            return False, 0, DAILY_TOKEN_LIMIT

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Returns all-time totals AND today's usage for the /stats command."""
        try:
            get_shared_pool()
        except Exception:
            return {}

        sql_all = (
            "SELECT COALESCE(SUM(input_tokens), 0), "
            "       COALESCE(SUM(output_tokens), 0), "
            "       COALESCE(SUM(total_tokens), 0), "
            "       COUNT(*) "
            "FROM token_usage;"
        )
        sql_today = (
            "SELECT COALESCE(SUM(input_tokens), 0), "
            "       COALESCE(SUM(output_tokens), 0), "
            "       COALESCE(SUM(total_tokens), 0), "
            "       COUNT(*) "
            "FROM token_usage WHERE created_at >= CURRENT_DATE;"
        )

        def _do(pool):
            with pool.connection() as conn:
                row_all   = conn.execute(sql_all).fetchone()
                row_today = conn.execute(sql_today).fetchone()
            return row_all, row_today

        try:
            row_all, row_today = self._with_retry(_do)

            def _safe(row, idx):
                return int(row[idx] or 0) if row else 0

            in_all,   out_all,   tot_all,   reqs_all   = (_safe(row_all, 0),   _safe(row_all, 1),   _safe(row_all, 2),   _safe(row_all, 3))
            in_today, out_today, tot_today, reqs_today = (_safe(row_today, 0), _safe(row_today, 1), _safe(row_today, 2), _safe(row_today, 3))

            return {
                "total_input":    in_all,
                "total_output":   out_all,
                "grand_total":    tot_all,
                "total_requests": reqs_all,
                "today_input":    in_today,
                "today_output":   out_today,
                "today_total":    tot_today,
                "today_requests": reqs_today,
                "daily_limit":    DAILY_TOKEN_LIMIT,
                "today_remaining": max(0, DAILY_TOKEN_LIMIT - tot_today),
            }
        except Exception as e:
            logger.error("Failed to fetch global stats after retries", error=str(e))
            return {}
