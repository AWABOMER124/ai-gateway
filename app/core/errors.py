"""
Standardized error types for the AI Core platform.

These errors carry machine-readable codes and never expose
stack traces or internal details to clients.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class ErrorCode(str, Enum):
    # Auth & access
    AUTH_FAILED = "AUTH_FAILED"
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"
    TOOL_PERMISSION_DENIED = "TOOL_PERMISSION_DENIED"
    TOOL_APPROVAL_REQUIRED = "TOOL_APPROVAL_REQUIRED"

    # Execution
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_DISABLED = "TOOL_DISABLED"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"

    # Limits
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    SPEND_LIMIT_EXCEEDED = "SPEND_LIMIT_EXCEEDED"

    # Data
    KNOWLEDGE_NOT_FOUND = "KNOWLEDGE_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"

    # AI quality
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    HANDOFF_REQUIRED = "HANDOFF_REQUIRED"

    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# HTTP status code mapping
_CODE_TO_STATUS = {
    ErrorCode.AUTH_FAILED: 401,
    ErrorCode.TENANT_ACCESS_DENIED: 403,
    ErrorCode.TOOL_PERMISSION_DENIED: 403,
    ErrorCode.TOOL_APPROVAL_REQUIRED: 403,
    ErrorCode.TOOL_NOT_FOUND: 404,
    ErrorCode.TOOL_DISABLED: 403,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.SPEND_LIMIT_EXCEEDED: 429,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.LOW_CONFIDENCE: 200,  # not an HTTP error — returned in response body
    ErrorCode.HANDOFF_REQUIRED: 200,
    ErrorCode.TOOL_EXECUTION_FAILED: 502,
    ErrorCode.AI_PROVIDER_ERROR: 502,
    ErrorCode.KNOWLEDGE_NOT_FOUND: 404,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
}


class AICoreError(Exception):
    """Base exception for all AI Core platform errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.request_id = request_id
        super().__init__(message)

    @property
    def http_status(self) -> int:
        return _CODE_TO_STATUS.get(self.code, 500)

    def to_response(self) -> dict[str, Any]:
        """Client-safe error response (no stack traces, no secrets)."""
        resp: dict[str, Any] = {
            "error": {
                "code": self.code.value,
                "message": self.message,
            }
        }
        if self.request_id:
            resp["error"]["request_id"] = self.request_id
        if self.details:
            resp["error"]["details"] = self.details
        return resp


class AuthError(AICoreError):
    def __init__(self, message: str = "Authentication failed", **kw):
        super().__init__(ErrorCode.AUTH_FAILED, message, **kw)


class TenantAccessDenied(AICoreError):
    def __init__(self, message: str = "Access denied for this tenant", **kw):
        super().__init__(ErrorCode.TENANT_ACCESS_DENIED, message, **kw)


class ToolPermissionDenied(AICoreError):
    def __init__(self, tool_key: str, message: str = "", **kw):
        msg = message or f"Permission denied for tool: {tool_key}"
        super().__init__(ErrorCode.TOOL_PERMISSION_DENIED, msg, details={"tool": tool_key}, **kw)


class ToolApprovalRequired(AICoreError):
    def __init__(self, tool_key: str, reason: str = "Policy requires approval", **kw):
        super().__init__(
            ErrorCode.TOOL_APPROVAL_REQUIRED,
            f"Approval required for tool: {tool_key}",
            details={"tool": tool_key, "reason": reason},
            **kw,
        )


class ToolExecutionFailed(AICoreError):
    def __init__(self, tool_key: str, message: str, **kw):
        super().__init__(
            ErrorCode.TOOL_EXECUTION_FAILED, message,
            details={"tool": tool_key}, **kw,
        )


class RateLimited(AICoreError):
    def __init__(self, message: str = "Rate limit exceeded", **kw):
        super().__init__(ErrorCode.RATE_LIMITED, message, **kw)


class QuotaExceeded(AICoreError):
    def __init__(self, message: str = "Quota exceeded", **kw):
        super().__init__(ErrorCode.QUOTA_EXCEEDED, message, **kw)


class ValidationError(AICoreError):
    def __init__(self, message: str, details: Optional[dict] = None, **kw):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, details=details, **kw)
