"""
Provider data models — normalized results, errors, and metadata.

All provider adapters return ProviderResult. Vendor-specific formats
are never exposed to calling tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"
    INVALID_REQUEST = "invalid_request"


class AuthType(str, Enum):
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    NONE = "none"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"


@dataclass
class ProviderMeta:
    """Static metadata about a provider."""
    key: str
    display_name: str
    capabilities: list[str]
    enabled: bool = True
    supported_countries: list[str] = field(default_factory=list)
    auth_type: AuthType = AuthType.API_KEY
    timeout_seconds: int = 10
    priority: int = 100
    estimated_cost_per_call: float = 0.0
    rate_limit_rpm: Optional[int] = None
    data_classification: DataClassification = DataClassification.PUBLIC
    base_url: str = ""


@dataclass
class ProviderResult:
    """Normalized result from any provider."""
    provider: str
    capability: str
    status: ProviderStatus
    data: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    elapsed_ms: int = 0
    http_status: Optional[int] = None
    request_id: Optional[str] = None


@dataclass
class ProviderError:
    """Structured error from a provider attempt."""
    provider: str
    capability: str
    status: ProviderStatus
    message: str
    http_status: Optional[int] = None
    retryable: bool = False
    elapsed_ms: int = 0

    @property
    def is_retryable(self) -> bool:
        return self.status in (
            ProviderStatus.TIMEOUT,
            ProviderStatus.RATE_LIMITED,
            ProviderStatus.ERROR,
        )
