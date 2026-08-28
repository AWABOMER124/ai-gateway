"""Phone number validation tool."""
from __future__ import annotations

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.providers.router import route
from app.tools.registry import register_tool


@register_tool(
    key="phone.validate",
    product="core",
    description="Validate a phone number and return carrier/line type info.",
    risk_level=RiskLevel.READ_ONLY,
    allowed_products=["qiad", "wasla", "easy_delivery", "zawed", "legacy_personal"],
    input_schema={
        "type": "object",
        "properties": {
            "phone_number": {"type": "string", "minLength": 4, "maxLength": 20},
            "country_code": {"type": "string", "minLength": 2, "maxLength": 2, "default": ""},
        },
        "required": ["phone_number"],
    },
    timeout_seconds=10,
)
async def phone_validate(ctx: ExecutionContext, phone_number: str, country_code: str = "") -> dict:
    result = await route(ctx, "phone.validate", {
        "phone_number": phone_number,
        "country_code": country_code.upper(),
    })
    return result.data
