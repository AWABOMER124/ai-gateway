"""
Security — password hashing, signed session cookies, API key generation.
Stdlib only, deliberately: no bcrypt/argon2/itsdangerous dependency, proportionate
to a handful of internal dashboard accounts rather than a public-facing signup
surface. Always secrets.token_*/hmac.compare_digest — never random/plain ==.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time

PBKDF2_ITERATIONS = 260_000  # OWASP-recommended floor for PBKDF2-HMAC-SHA256


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(dk, bytes.fromhex(hash_hex))
    except (ValueError, AttributeError):
        return False


def _session_secret() -> bytes:
    s = os.getenv("DASHBOARD_SESSION_SECRET", "")
    if not s:
        raise RuntimeError("DASHBOARD_SESSION_SECRET not configured")
    return s.encode()


def create_session_token(user_id: str, role: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
    payload = f"{user_id}:{role}:{int(time.time()) + ttl_seconds}"
    sig = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def verify_session_token(token: str) -> dict | None:
    try:
        user_id, role, expires_at, sig = base64.urlsafe_b64decode(token.encode()).decode().rsplit(":", 3)
        expected = hmac.new(_session_secret(), f"{user_id}:{role}:{expires_at}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected) or int(expires_at) < time.time():
            return None
        return {"user_id": user_id, "role": role}
    except Exception:
        return None


def generate_api_key(env: str = "live") -> tuple[str, str, str]:
    """Returns (full_key, key_prefix, key_hash). The full key is only ever
    returned here — never persisted anywhere, only its sha256 hash is stored."""
    token = secrets.token_urlsafe(32)
    full_key = f"gwk_{env}_{token}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, full_key[:16] + "…", key_hash


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
