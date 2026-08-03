"""
Shared Postgres connection pool for all agent services.

Before this, every service file (task_store, email_store, olivery_edit_store,
olivery_report_store, waslak_draft_store, waslak_insight_store, file_processor,
audit_log) opened and closed a brand new psycopg2 connection on every single
call via a copy-pasted _get_conn(). Under concurrent load (parallel Telegram
messages, n8n polling) that churns Postgres connections unnecessarily. This
module gives them one small shared pool instead.
"""
import os
import threading
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None
_lock = threading.Lock()


def _dsn() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        return db_url
    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'awab_ai')} "
        f"user={os.getenv('POSTGRES_USER', 'awab_ai')} "
        f"password={os.getenv('POSTGRES_PASSWORD', '')}"
    )


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=_dsn())
    return _pool


@contextmanager
def pooled_cursor(commit: bool = True):
    """
    Borrow a connection from the shared pool, yield a RealDictCursor.
    Commits on success (unless commit=False, for reads), rolls back on
    exception, and always returns the connection to the pool — never closes
    it outright, so pool bookkeeping stays consistent across the app's
    lifetime.
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
