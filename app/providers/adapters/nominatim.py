"""Nominatim (OpenStreetMap) provider adapter — free geocoding, no key required."""
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

_BASE = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": "AICore/1.0 (ai-gateway)"}


class NominatimProvider(BaseProvider):
    _meta = ProviderMeta(
        key="nominatim",
        display_name="Nominatim (OSM)",
        capabilities=["geo.geocode", "geo.reverse_geocode"],
        auth_type=AuthType.NONE,
        timeout_seconds=10,
        priority=20,
        estimated_cost_per_call=0.0,
        rate_limit_rpm=60,
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
        if capability == "geo.geocode":
            return await self._geocode(params, timeout)
        if capability == "geo.reverse_geocode":
            return await self._reverse(params, timeout)
        return ProviderResult(
            provider="nominatim", capability=capability,
            status=ProviderStatus.INVALID_REQUEST,
            data={"error": f"Unsupported capability: {capability}"},
        )

    async def _geocode(self, params: dict, timeout: float | None) -> ProviderResult:
        client = get_http_client()
        resp = await client.get(
            f"{_BASE}/search",
            params={"q": params["address"], "format": "json", "limit": 5, "addressdetails": 1},
            headers=_HEADERS,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return ProviderResult(
                provider="nominatim", capability="geo.geocode",
                status=ProviderStatus.ERROR, http_status=resp.status_code,
                data={"error": resp.text},
            )
        results = resp.json()
        if not results:
            return ProviderResult(
                provider="nominatim", capability="geo.geocode",
                status=ProviderStatus.SUCCESS, http_status=200,
                data={"results": [], "count": 0},
            )
        parsed = []
        for r in results:
            addr = r.get("address", {})
            parsed.append({
                "latitude": float(r.get("lat", 0)),
                "longitude": float(r.get("lon", 0)),
                "display_name": r.get("display_name", ""),
                "type": r.get("type", ""),
                "country": addr.get("country", ""),
                "country_code": addr.get("country_code", ""),
                "city": addr.get("city") or addr.get("town") or addr.get("village", ""),
                "road": addr.get("road", ""),
                "postcode": addr.get("postcode", ""),
            })
        return ProviderResult(
            provider="nominatim", capability="geo.geocode",
            status=ProviderStatus.SUCCESS, http_status=200,
            data={"results": parsed, "count": len(parsed)},
        )

    async def _reverse(self, params: dict, timeout: float | None) -> ProviderResult:
        client = get_http_client()
        resp = await client.get(
            f"{_BASE}/reverse",
            params={
                "lat": params["latitude"], "lon": params["longitude"],
                "format": "json", "addressdetails": 1,
            },
            headers=_HEADERS,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return ProviderResult(
                provider="nominatim", capability="geo.reverse_geocode",
                status=ProviderStatus.ERROR, http_status=resp.status_code,
                data={"error": resp.text},
            )
        body = resp.json()
        if "error" in body:
            return ProviderResult(
                provider="nominatim", capability="geo.reverse_geocode",
                status=ProviderStatus.SUCCESS, http_status=200,
                data={"address": None, "error": body["error"]},
            )
        addr = body.get("address", {})
        return ProviderResult(
            provider="nominatim", capability="geo.reverse_geocode",
            status=ProviderStatus.SUCCESS, http_status=200,
            data={
                "display_name": body.get("display_name", ""),
                "latitude": float(body.get("lat", 0)),
                "longitude": float(body.get("lon", 0)),
                "country": addr.get("country", ""),
                "country_code": addr.get("country_code", ""),
                "city": addr.get("city") or addr.get("town") or addr.get("village", ""),
                "road": addr.get("road", ""),
                "postcode": addr.get("postcode", ""),
                "neighbourhood": addr.get("neighbourhood", ""),
            },
        )

    async def health_check(self) -> bool:
        try:
            client = get_http_client()
            resp = await client.get(
                f"{_BASE}/search", params={"q": "test", "format": "json", "limit": 1},
                headers=_HEADERS, timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False


provider_registry.register(NominatimProvider())
