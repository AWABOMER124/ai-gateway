"""Shared authentication helpers for the operational admin surface."""

from __future__ import annotations

import base64
import binascii
import hmac


def is_valid_admin_authorization(authorization: str, secret: str) -> bool:
    """Accept service Bearer auth or browser-compatible HTTP Basic auth."""
    if not authorization or not secret:
        return False

    scheme, _, credentials = authorization.partition(" ")
    credentials = credentials.strip()
    if not credentials:
        return False

    if scheme.lower() == "bearer":
        return hmac.compare_digest(credentials, secret)

    if scheme.lower() != "basic":
        return False

    try:
        decoded = base64.b64decode(credentials, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False

    username, separator, password = decoded.partition(":")
    return (
        bool(separator)
        and hmac.compare_digest(username, "admin")
        and hmac.compare_digest(password, secret)
    )
