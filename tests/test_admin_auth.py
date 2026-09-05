import base64

from app.core.admin_auth import is_valid_admin_authorization


def _basic(username: str, password: str) -> str:
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {credentials}"


def test_accepts_bearer_service_secret():
    assert is_valid_admin_authorization("Bearer production-secret", "production-secret")


def test_accepts_browser_basic_auth():
    assert is_valid_admin_authorization(_basic("admin", "production-secret"), "production-secret")


def test_rejects_wrong_basic_username_or_password():
    assert not is_valid_admin_authorization(_basic("operator", "production-secret"), "production-secret")
    assert not is_valid_admin_authorization(_basic("admin", "wrong-secret"), "production-secret")


def test_rejects_malformed_or_unsupported_authorization():
    assert not is_valid_admin_authorization("Basic not-base64!", "production-secret")
    assert not is_valid_admin_authorization("Digest token", "production-secret")
    assert not is_valid_admin_authorization("", "production-secret")
