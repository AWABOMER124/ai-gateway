"""
Waslak Client — REST wrapper for the Waslak Merchant OS "AI agent" API
(/api/agent/v1/*). Reads credentials exclusively from environment variables.
Raises WaslakNotConfigured if env is incomplete.
"""
import os
import httpx


class WaslakNotConfigured(Exception):
    pass


class WaslakAPIError(Exception):
    """Non-2xx Waslak API error. Carries status_code + message."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Waslak API error {status_code}: {message}")


class WaslakRateLimited(WaslakAPIError):
    """429 — 30 store drafts/hour/key limit hit."""


class WaslakValidationError(WaslakAPIError):
    """422 — business-rule validation failed on Waslak's side."""


class WaslakClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("WASLAK_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("WASLAK_API_KEY", "")
        missing = [k for k, v in {
            "WASLAK_BASE_URL": self.base_url,
            "WASLAK_API_KEY": self.api_key,
        }.items() if not v]
        if missing:
            raise WaslakNotConfigured(f"Missing env vars: {', '.join(missing)}")

    async def _request(self, method: str, path: str, json_body: dict | None = None):
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=json_body,
            )
        try:
            body = r.json()
        except Exception:
            body = {}

        if r.status_code == 429:
            raise WaslakRateLimited(429, body.get("message", "Rate limit exceeded (30/hour)"))
        if r.status_code == 422:
            raise WaslakValidationError(422, body.get("message", "Validation failed"))
        if r.status_code >= 400:
            raise WaslakAPIError(r.status_code, body.get("message", f"HTTP {r.status_code}"))
        return body.get("data", {})

    async def submit_draft(self, payload: dict) -> dict:
        """POST /api/agent/v1/stores/drafts — scope stores:draft, 30/hour/key."""
        return await self._request("POST", "/api/agent/v1/stores/drafts", json_body=payload)

    async def get_draft(self, draft_id: str) -> dict:
        """GET /api/agent/v1/stores/drafts/{id} — scope stores:draft. No webhook exists; poll only."""
        return await self._request("GET", f"/api/agent/v1/stores/drafts/{draft_id}")

    async def list_drafts(self) -> list:
        """GET /api/agent/v1/stores/drafts — scope stores:draft, last 50 for the distributor."""
        data = await self._request("GET", "/api/agent/v1/stores/drafts")
        return data if isinstance(data, list) else []

    async def list_merchants(self) -> list:
        """GET /api/agent/v1/merchants — scope merchants:read."""
        data = await self._request("GET", "/api/agent/v1/merchants")
        return data if isinstance(data, list) else []

    async def get_merchant_orders(self, merchant_id: str) -> dict:
        """GET /api/agent/v1/merchants/{id}/orders — scope orders:read."""
        return await self._request("GET", f"/api/agent/v1/merchants/{merchant_id}/orders")
