"""
Auth — accepts EITHER the legacy shared GATEWAY_API_KEY (full access, used by
Telegram/n8n) OR a scoped integration API key (issued from the dashboard,
/dashboard/api-keys) carrying the specific scope a route requires.
"""
import os
import hmac
from fastapi import Header, HTTPException, status
from app.services import api_keys as api_key_store


async def _legacy_secret_matches(x_api_key: str | None) -> bool:
    expected = os.getenv("GATEWAY_API_KEY", "")
    return bool(expected and x_api_key and hmac.compare_digest(x_api_key, expected))


def require_scope(scope: str):
    async def dependency(
        x_api_key: str | None = Header(None, alias="X-API-Key"),
        authorization: str | None = Header(None),
    ) -> dict:
        if await _legacy_secret_matches(x_api_key):
            return {"auth": "legacy", "key_id": None, "scopes": ["*"]}

        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
        elif x_api_key:
            token = x_api_key
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API key")

        key_row = await api_key_store.get_key_by_token(token)
        if not key_row or key_row["revoked_at"] is not None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key")
        if "*" not in key_row["scopes"] and scope not in key_row["scopes"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"API key missing required scope: {scope}")

        await api_key_store.touch_last_used(key_row["id"])
        return {"auth": "scoped", "key_id": key_row["id"], "scopes": key_row["scopes"]}

    return dependency
