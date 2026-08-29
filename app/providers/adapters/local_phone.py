"""Local phone validation provider — basic format validation, no external API."""
from __future__ import annotations

import re
from typing import Any, Optional

from app.providers.base import BaseProvider
from app.providers.models import (
    AuthType,
    DataClassification,
    ProviderMeta,
    ProviderResult,
    ProviderStatus,
)
from app.providers.registry import provider_registry

_COUNTRY_CODES = {
    "SA": "+966", "AE": "+971", "EG": "+20", "JO": "+962",
    "KW": "+965", "BH": "+973", "QA": "+974", "OM": "+968",
    "IQ": "+964", "LB": "+961", "SY": "+963", "YE": "+967",
    "SD": "+249", "LY": "+218", "TN": "+216", "DZ": "+213",
    "MA": "+212", "US": "+1", "GB": "+44", "TR": "+90",
    "IN": "+91", "PK": "+92", "DE": "+49", "FR": "+33",
}

_DIGITS_RE = re.compile(r"\d")


def _clean_phone(phone: str) -> str:
    return re.sub(r"[\s\-\(\)\.]+", "", phone)


class LocalPhoneProvider(BaseProvider):
    _meta = ProviderMeta(
        key="local_phone",
        display_name="Local Phone Validator",
        capabilities=["phone.validate"],
        auth_type=AuthType.NONE,
        timeout_seconds=2,
        priority=10,
        estimated_cost_per_call=0.0,
        data_classification=DataClassification.PUBLIC,
        base_url="",
    )

    def meta(self) -> ProviderMeta:
        return self._meta

    async def execute(
        self,
        capability: str,
        params: dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ProviderResult:
        if capability != "phone.validate":
            return ProviderResult(
                provider="local_phone", capability=capability,
                status=ProviderStatus.INVALID_REQUEST,
                data={"error": f"Unsupported: {capability}"},
            )

        raw = params.get("phone_number", "")
        country = params.get("country_code", "").upper()
        cleaned = _clean_phone(raw)
        digits = _DIGITS_RE.findall(cleaned)
        digit_count = len(digits)

        if not cleaned or digit_count < 4:
            return ProviderResult(
                provider="local_phone", capability="phone.validate",
                status=ProviderStatus.SUCCESS, http_status=200,
                data={
                    "phone_number": raw,
                    "valid": False,
                    "reason": "Too few digits",
                    "formatted": "",
                    "country_code": country,
                },
            )

        has_plus = cleaned.startswith("+")
        has_double_zero = cleaned.startswith("00")

        if not has_plus and has_double_zero:
            cleaned = "+" + cleaned[2:]
            has_plus = True

        if not has_plus and country and country in _COUNTRY_CODES:
            prefix = _COUNTRY_CODES[country]
            if cleaned.startswith("0"):
                cleaned = prefix + cleaned[1:]
            else:
                cleaned = prefix + cleaned
            has_plus = True

        valid = 7 <= digit_count <= 15
        detected_country = ""
        if has_plus:
            for cc, prefix in _COUNTRY_CODES.items():
                if cleaned.startswith(prefix):
                    detected_country = cc
                    break

        return ProviderResult(
            provider="local_phone", capability="phone.validate",
            status=ProviderStatus.SUCCESS, http_status=200,
            data={
                "phone_number": raw,
                "valid": valid,
                "reason": "Valid format" if valid else f"Invalid digit count ({digit_count})",
                "formatted": cleaned if has_plus else raw,
                "digit_count": digit_count,
                "country_code": detected_country or country,
                "has_international_prefix": has_plus,
            },
        )

    async def health_check(self) -> bool:
        return True


provider_registry.register(LocalPhoneProvider())
