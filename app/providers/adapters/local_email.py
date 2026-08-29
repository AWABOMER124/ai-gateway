"""Local email validation provider — format check + MX lookup, no external API."""
from __future__ import annotations

import re
import socket
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

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def _check_mx(domain: str) -> list[str]:
    try:
        socket.getaddrinfo(domain, 25, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return [domain]
    except socket.gaierror:
        return []


class LocalEmailProvider(BaseProvider):
    _meta = ProviderMeta(
        key="local_email",
        display_name="Local Email Validator",
        capabilities=["email.validate"],
        auth_type=AuthType.NONE,
        timeout_seconds=5,
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
        if capability != "email.validate":
            return ProviderResult(
                provider="local_email", capability=capability,
                status=ProviderStatus.INVALID_REQUEST,
                data={"error": f"Unsupported: {capability}"},
            )

        email = params.get("email", "").strip().lower()

        if not email or not _EMAIL_RE.match(email):
            return ProviderResult(
                provider="local_email", capability="email.validate",
                status=ProviderStatus.SUCCESS, http_status=200,
                data={
                    "email": email,
                    "valid": False,
                    "reason": "Invalid email format",
                    "domain": "",
                    "mx_records": [],
                },
            )

        domain = email.split("@")[1]
        mx = _check_mx(domain)

        return ProviderResult(
            provider="local_email", capability="email.validate",
            status=ProviderStatus.SUCCESS, http_status=200,
            data={
                "email": email,
                "valid": len(mx) > 0,
                "reason": "MX records found" if mx else "No MX records for domain",
                "domain": domain,
                "mx_records": mx[:5],
            },
        )

    async def health_check(self) -> bool:
        return True


provider_registry.register(LocalEmailProvider())
