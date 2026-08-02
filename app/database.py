"""
database.py — إدارة الاتصال بـ PostgreSQL.
"""

from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from app.config import settings


def get_connection():
    """فتح اتصال مباشر بـ PostgreSQL."""
    return psycopg2.connect(
        settings.database_url,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@contextmanager
def db_cursor():
    """
    Context manager يفتح اتصال، ينفّذ العمليات، يغلق تلقائياً.

    الاستخدام:
        with db_cursor() as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
