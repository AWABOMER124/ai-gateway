"""Currency conversion tool."""
from __future__ import annotations

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.providers.router import route
from app.tools.registry import register_tool


@register_tool(
    key="currency.convert",
    product="core",
    description="Convert an amount between currencies using live exchange rates.",
    risk_level=RiskLevel.READ_ONLY,
    allowed_products=["qiad", "wasla", "easy_delivery", "zawed", "legacy_personal"],
    input_schema={
        "type": "object",
        "properties": {
            "from_currency": {"type": "string", "minLength": 3, "maxLength": 3},
            "to_currency": {"type": "string", "minLength": 3, "maxLength": 3},
            "amount": {"type": "number", "minimum": 0},
        },
        "required": ["from_currency", "to_currency", "amount"],
    },
    timeout_seconds=10,
)
async def currency_convert(
    ctx: ExecutionContext,
    from_currency: str,
    to_currency: str,
    amount: float,
) -> dict:
    result = await route(ctx, "currency.convert", {
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "amount": amount,
    })
    return result.data
