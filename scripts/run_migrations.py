"""Apply pending SQL migrations before the API starts.

The runner is safe across concurrent replicas: a Postgres advisory lock
serializes execution and each migration is recorded only after commit.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"
LOCK_ID = 764_521_012


def dsn() -> str:
    if value := os.getenv("DATABASE_URL", "").strip():
        return value
    return " ".join(
        [
            f"host={os.getenv('POSTGRES_HOST', 'localhost')}",
            f"port={os.getenv('POSTGRES_PORT', '5432')}",
            f"dbname={os.getenv('POSTGRES_DB', 'awab_ai')}",
            f"user={os.getenv('POSTGRES_USER', 'awab_ai')}",
            f"password={os.getenv('POSTGRES_PASSWORD', '')}",
        ]
    )


def main() -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    with psycopg2.connect(dsn()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
            try:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        filename TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                connection.commit()

                for path in files:
                    cursor.execute(
                        "SELECT 1 FROM schema_migrations WHERE filename = %s",
                        (path.name,),
                    )
                    if cursor.fetchone():
                        continue

                    try:
                        cursor.execute(path.read_text(encoding="utf-8"))
                        cursor.execute(
                            "INSERT INTO schema_migrations (filename) VALUES (%s)",
                            (path.name,),
                        )
                        connection.commit()
                        print(f"migration applied: {path.name}", flush=True)
                    except Exception:
                        connection.rollback()
                        raise
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
                connection.commit()


if __name__ == "__main__":
    main()
