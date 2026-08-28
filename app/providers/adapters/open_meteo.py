"""Open-Meteo provider adapter — free weather API, no key required."""
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

_BASE = "https://api.open-meteo.com/v1"

_CURRENT_PARAMS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "precipitation,wind_speed_10m,wind_direction_10m,weather_code"
)

_FORECAST_DAILY = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "precipitation_sum,wind_speed_10m_max"
)

_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


class OpenMeteoProvider(BaseProvider):
    _meta = ProviderMeta(
        key="open_meteo",
        display_name="Open-Meteo",
        capabilities=["weather.current", "weather.forecast"],
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
        if capability == "weather.current":
            return await self._current(params, timeout)
        if capability == "weather.forecast":
            return await self._forecast(params, timeout)
        return ProviderResult(
            provider="open_meteo",
            capability=capability,
            status=ProviderStatus.INVALID_REQUEST,
            data={"error": f"Unsupported capability: {capability}"},
        )

    async def _current(self, params: dict, timeout: float | None) -> ProviderResult:
        client = get_http_client()
        resp = await client.get(
            f"{_BASE}/forecast",
            params={
                "latitude": params["latitude"],
                "longitude": params["longitude"],
                "current": _CURRENT_PARAMS,
                "timezone": "auto",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return ProviderResult(
                provider="open_meteo", capability="weather.current",
                status=ProviderStatus.ERROR, http_status=resp.status_code,
                data={"error": resp.text},
            )
        body = resp.json()
        cur = body.get("current", {})
        return ProviderResult(
            provider="open_meteo",
            capability="weather.current",
            status=ProviderStatus.SUCCESS,
            http_status=200,
            data={
                "temperature_c": cur.get("temperature_2m"),
                "feels_like_c": cur.get("apparent_temperature"),
                "humidity_pct": cur.get("relative_humidity_2m"),
                "precipitation_mm": cur.get("precipitation"),
                "wind_speed_kmh": cur.get("wind_speed_10m"),
                "wind_direction_deg": cur.get("wind_direction_10m"),
                "condition": _WMO_CODES.get(cur.get("weather_code", -1), "Unknown"),
                "weather_code": cur.get("weather_code"),
                "timezone": body.get("timezone"),
                "location": {
                    "latitude": body.get("latitude"),
                    "longitude": body.get("longitude"),
                    "elevation": body.get("elevation"),
                },
            },
        )

    async def _forecast(self, params: dict, timeout: float | None) -> ProviderResult:
        days = min(params.get("days", 3), 7)
        client = get_http_client()
        resp = await client.get(
            f"{_BASE}/forecast",
            params={
                "latitude": params["latitude"],
                "longitude": params["longitude"],
                "daily": _FORECAST_DAILY,
                "timezone": "auto",
                "forecast_days": days,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return ProviderResult(
                provider="open_meteo", capability="weather.forecast",
                status=ProviderStatus.ERROR, http_status=resp.status_code,
                data={"error": resp.text},
            )
        body = resp.json()
        daily = body.get("daily", {})
        dates = daily.get("time", [])
        forecast = []
        for i, date in enumerate(dates):
            forecast.append({
                "date": date,
                "temp_max_c": daily.get("temperature_2m_max", [None])[i] if i < len(daily.get("temperature_2m_max", [])) else None,
                "temp_min_c": daily.get("temperature_2m_min", [None])[i] if i < len(daily.get("temperature_2m_min", [])) else None,
                "precipitation_mm": daily.get("precipitation_sum", [None])[i] if i < len(daily.get("precipitation_sum", [])) else None,
                "wind_max_kmh": daily.get("wind_speed_10m_max", [None])[i] if i < len(daily.get("wind_speed_10m_max", [])) else None,
                "condition": _WMO_CODES.get(
                    daily.get("weather_code", [None])[i] if i < len(daily.get("weather_code", [])) else -1,
                    "Unknown",
                ),
            })
        return ProviderResult(
            provider="open_meteo",
            capability="weather.forecast",
            status=ProviderStatus.SUCCESS,
            http_status=200,
            data={
                "days": forecast,
                "timezone": body.get("timezone"),
                "location": {
                    "latitude": body.get("latitude"),
                    "longitude": body.get("longitude"),
                },
            },
        )

    async def health_check(self) -> bool:
        try:
            client = get_http_client()
            resp = await client.get(f"{_BASE}/forecast", params={
                "latitude": 0, "longitude": 0, "current": "temperature_2m",
            }, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


provider_registry.register(OpenMeteoProvider())
