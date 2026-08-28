"""Weather tools — current conditions and forecast."""
from __future__ import annotations

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.providers.router import route
from app.tools.registry import register_tool


@register_tool(
    key="weather.current",
    product="core",
    description="Get current weather conditions for a location (lat/lon).",
    risk_level=RiskLevel.READ_ONLY,
    allowed_products=["qiad", "wasla", "easy_delivery", "zawed", "legacy_personal"],
    input_schema={
        "type": "object",
        "properties": {
            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
        },
        "required": ["latitude", "longitude"],
    },
    timeout_seconds=15,
)
async def weather_current(ctx: ExecutionContext, latitude: float, longitude: float) -> dict:
    result = await route(ctx, "weather.current", {"latitude": latitude, "longitude": longitude})
    return result.data


@register_tool(
    key="weather.forecast",
    product="core",
    description="Get weather forecast for a location (lat/lon), up to 7 days.",
    risk_level=RiskLevel.READ_ONLY,
    allowed_products=["qiad", "wasla", "easy_delivery", "zawed", "legacy_personal"],
    input_schema={
        "type": "object",
        "properties": {
            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
            "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 3},
        },
        "required": ["latitude", "longitude"],
    },
    timeout_seconds=15,
)
async def weather_forecast(ctx: ExecutionContext, latitude: float, longitude: float, days: int = 3) -> dict:
    result = await route(ctx, "weather.forecast", {"latitude": latitude, "longitude": longitude, "days": days})
    return result.data
