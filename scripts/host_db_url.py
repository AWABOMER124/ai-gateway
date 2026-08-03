#!/usr/bin/env python3
"""
Resolves DATABASE_URL (as used inside Docker containers — currently
awab-ai-postgres:5432, an internal container-network hostname) to the
equivalent connection string reachable from the bare host: 127.0.0.1 on the
published port (5438). Used by host-side scripts (backups, migrations) that
run outside any container and can't resolve container-network hostnames.

Kept as one shared helper instead of duplicating a sed pattern in every
script, after a hostname change (host.docker.internal -> awab-ai-postgres,
2026-08-02 network fix) silently broke a sed-based substitution in
backup_db.sh that only matched the old literal hostname.
"""
import os
import sys
from urllib.parse import urlsplit, urlunsplit

HOST_PORT = "5438"


def main() -> None:
    url = os.environ["DATABASE_URL"]
    parts = urlsplit(url)
    netloc = parts.netloc
    creds = netloc.rsplit("@", 1)[0] if "@" in netloc else None
    new_netloc = f"{creds}@127.0.0.1:{HOST_PORT}" if creds else f"127.0.0.1:{HOST_PORT}"
    print(urlunsplit((parts.scheme, new_netloc, parts.path, parts.query, parts.fragment)))


if __name__ == "__main__":
    main()
