#!/usr/bin/env python3
"""
create_dashboard_user.py — bootstrap a dashboard login account.

No in-app sign-up/invite UI (disproportionate for a small team) — an owner
runs this to add every new team member. Run inside the container's Python
env (same DATABASE_URL as the app), e.g.:

    docker exec -it awab-ai-gateway python scripts/create_dashboard_user.py

or from the host with DATABASE_URL exported to the container-reachable form
(see scripts/host_db_url.py) if running outside Docker.
"""
import getpass
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app")  # container WORKDIR; harmless if already on path

import psycopg2
import os

from app.services.security import hash_password


def main() -> None:
    email = input("Email: ").strip()
    if not email:
        print("Email required.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    password2 = getpass.getpass("Confirm password: ")
    if password != password2:
        print("Passwords don't match.")
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)

    role = input("Role [owner/member] (default: member): ").strip().lower() or "member"
    if role not in ("owner", "member"):
        print("Role must be 'owner' or 'member'.")
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL", "")
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM dashboard_users WHERE email = %s", (email,))
            if cur.fetchone():
                print(f"A user with email {email} already exists.")
                sys.exit(1)
            cur.execute(
                "INSERT INTO dashboard_users (id, email, password_hash, role, created_at) VALUES (%s,%s,%s,%s,%s)",
                (str(uuid.uuid4()), email, hash_password(password), role, datetime.now(timezone.utc)),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Created {role} account for {email}.")


if __name__ == "__main__":
    main()
