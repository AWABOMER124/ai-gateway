"""Geocoding tools — address to coordinates and reverse."""
from __future__ import annotations

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.providers.router import route
from app.tools.registry import register_tool


@register_tool(
    key="geo.geocode",
    product="core",
    description="Convert an address string to latitude/longitude coordinates.",
    risk_level=RiskLevel.READ_ONLY,
    allowed_products=["qiad", "wasla", "easy_delivery", "zawed", "legacy_personal"],
    input_schema={
        "type": "object",
        "properties": {
            "address": {"type": "string", "minLength": 2, "maxLength": 500},
        },
        "required": ["address"],
    },
    timeout_seconds=15,
)
async def geo_geocode(ctx: ExecutionContext, address: str) -> dict:
    result = await route(ctx, "geo.geocode", {"address": address})
    return result.data


@register_tool(
    key="geo.reverse_geocode",
    product="core",
    description="Convert latitude/longitude to a human-readable address.",
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
async def geo_reverse_geocode(ctx: ExecutionContext, latitude: float, longitude: float) -> dict:
    result = await route(ctx, "geo.reverse_geocode", {"latitude": latitude, "longitude": longitude})
    return result.data
