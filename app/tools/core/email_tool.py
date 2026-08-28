"""Email validation tool."""
from __future__ import annotations

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.providers.router import route
from app.tools.registry import register_tool


@register_tool(
    key="email.validate",
    product="core",
    description="Validate an email address format and check MX records.",
    risk_level=RiskLevel.READ_ONLY,
    allowed_products=["qiad", "wasla", "easy_delivery", "zawed", "legacy_personal"],
    input_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string", "format": "email", "maxLength": 320},
        },
        "required": ["email"],
    },
    timeout_seconds=10,
)
async def email_validate(ctx: ExecutionContext, email: str) -> dict:
    result = await route(ctx, "email.validate", {"email": email.lower().strip()})
    return result.data
