"""ExchangeRate-API provider adapter — free currency conversion, no key required."""
from __future__ import annotations

from typing import Any, Optional

from app.providers.base import BaseProvider
from app.providers.http_client import get_http_client
from app.providers.models import (
    AuthType,
    DataClassification,
    ProviderMeta,
    ProviderResult,
    ProviderStatus,
)
from app.providers.registry import provider_registry

_BASE = "https://open.er-api.com/v6"


class ExchangeRateProvider(BaseProvider):
    _meta = ProviderMeta(
        key="exchangerate_api",
        display_name="ExchangeRate-API",
        capabilities=["currency.convert"],
        auth_type=AuthType.NONE,
        timeout_seconds=10,
        priority=10,
        estimated_cost_per_call=0.0,
        data_classification=DataClassification.PUBLIC,
        base_url=_BASE,
    )

    def meta(self) -> ProviderMeta:
        return self._meta

    async def execute(
        self,
        capability: str,
        params: dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ProviderResult:
        if capability != "currency.convert":
            return ProviderResult(
                provider="exchangerate_api",
                capability=capability,
                status=ProviderStatus.INVALID_REQUEST,
                data={"error": f"Unsupported capability: {capability}"},
            )

        from_cur = params["from_currency"].upper()
        to_cur = params["to_currency"].upper()
        amount = params["amount"]

        client = get_http_client()
        resp = await client.get(
            f"{_BASE}/latest/{from_cur}",
            timeout=timeout,
        )

        if resp.status_code != 200:
            return ProviderResult(
                provider="exchangerate_api",
                capability="currency.convert",
                status=ProviderStatus.ERROR,
                http_status=resp.status_code,
                data={"error": resp.text},
            )

        body = resp.json()
        if body.get("result") != "success":
            return ProviderResult(
                provider="exchangerate_api",
                capability="currency.convert",
                status=ProviderStatus.ERROR,
                data={"error": body.get("error-type", "Unknown API error")},
            )

        rates = body.get("rates", {})
        if to_cur not in rates:
            return ProviderResult(
                provider="exchangerate_api",
                capability="currency.convert",
                status=ProviderStatus.INVALID_REQUEST,
                data={"error": f"Unknown target currency: {to_cur}"},
            )

        rate = rates[to_cur]
        converted = round(amount * rate, 4)

        return ProviderResult(
            provider="exchangerate_api",
            capability="currency.convert",
            status=ProviderStatus.SUCCESS,
            http_status=200,
            data={
                "from_currency": from_cur,
                "to_currency": to_cur,
                "amount": amount,
                "rate": rate,
                "converted": converted,
                "last_updated": body.get("time_last_update_utc"),
            },
        )

    async def health_check(self) -> bool:
        try:
            client = get_http_client()
            resp = await client.get(f"{_BASE}/latest/USD", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


provider_registry.register(ExchangeRateProvider())
