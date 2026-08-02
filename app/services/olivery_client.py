"""
Olivery API Client — JSON-RPC 2.0 HTTP client.
Reads credentials exclusively from environment variables.
Raises OliveryNotConfigured if env is incomplete.
"""
import os
import httpx
from typing import Any


class OliveryNotConfigured(Exception):
    pass


class OliveryClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OLIVERY_BASE_URL", "").rstrip("/")
        self.db = os.getenv("OLIVERY_DB", "")
        self.login = os.getenv("OLIVERY_LOGIN", "")
        self.password = os.getenv("OLIVERY_PASSWORD", "")
        missing = [k for k, v in {
            "OLIVERY_BASE_URL": self.base_url,
            "OLIVERY_DB": self.db,
            "OLIVERY_LOGIN": self.login,
            "OLIVERY_PASSWORD": self.password,
        }.items() if not v]
        if missing:
            raise OliveryNotConfigured(f"Missing env vars: {', '.join(missing)}")

    def _auth_params(self, extra: dict | None = None) -> dict:
        params: dict[str, Any] = {
            "db": self.db,
            "login": self.login,
            "password": self.password,
            "context": {"lang": "en_US"},
        }
        if extra:
            params.update(extra)
        return params

    async def _rpc(self, method_path: str, params: dict, http_method: str = "GET") -> Any:
        payload = {"jsonrpc": "2.0", "params": params}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(
                method=http_method,
                url=f"{self.base_url}/{method_path}",
                headers={"Content-Type": "application/json"},
                content=__import__("json").dumps(payload).encode(),
            )
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(f"Olivery API error: {data['error']}")
            result = data.get("result", {})
            return result.get("response", result) if isinstance(result, dict) else result

    async def fetch(self, report_type: str, filters: dict) -> list[dict]:
        if report_type == "order_tracking":
            order_ids = filters.get("order_ids", [])
            if not order_ids:
                return []
            raw = await self._rpc("order", self._auth_params({"order_ids": order_ids}))
            return raw if isinstance(raw, list) else ([raw] if raw else [])

        if report_type == "operation_daily":
            date = filters.get("date", "")
            raw = await self._rpc("order", self._auth_params({"date": date, "limit": 200}))
            return raw if isinstance(raw, list) else []

        if report_type == "delayed_shipments":
            raw = await self._rpc("order", self._auth_params({
                "state": "out_for_delivery",
                "delayed": True,
                "limit": 100,
            }))
            return raw if isinstance(raw, list) else []

        if report_type in ("cod_summary", "finance_settlement"):
            raw = await self._rpc("settlement", self._auth_params(filters))
            return raw if isinstance(raw, list) else []

        return []

    async def edit_order(self, order_id: str, vals: dict) -> dict:
        result = await self._rpc(
            "edit_order",
            self._auth_params({"order_id": order_id, "vals": vals}),
            http_method="POST",
        )
        return result if isinstance(result, dict) else {"result": result}
