"""
Service-to-service authentication for the AI Core platform.

Products (QIAD, Wasla) authenticate to AI Core using short-lived JWTs
with verified claims. This is separate from the existing dashboard/API-key
auth (app/services/security.py, app/routers/_auth.py) which continues to
work for legacy integrations.

JWT format:
{
  "iss": "qiad",              # issuer — the calling product
  "aud": "ai-core",           # audience — always "ai-core"
  "sub": "user_uuid",         # the authenticated user in the product
  "org": "org_uuid",          # organization/tenant ID in the product
  "permissions": ["contacts.view", "conversations.view", ...],
  "exp": 1234567890,
  "iat": 1234567890,
  "jti": "request_uuid"
}

Verification uses HMAC-SHA256 with a shared secret per product.
In production, this should be replaced with asymmetric keys (RS256/ES256).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import base64
import os
import time
from typing import Optional

from app.core.context import ExecutionContext, Actor, ActorType, Product, AgentMode
from app.core.errors import AuthError


# Product secrets — each product gets its own shared secret
def _get_product_secret(issuer: str) -> Optional[str]:
    """Load the shared secret for a product issuer from env."""
    key = f"AI_CORE_SECRET_{issuer.upper()}"
    return os.getenv(key)


def _get_master_secret() -> Optional[str]:
    return os.getenv("AI_CORE_SERVICE_SECRET")


def create_service_token(
    issuer: str,
    subject: str,
    organization_id: str,
    permissions: list[str],
    ttl_seconds: int = 300,
    extra_claims: Optional[dict] = None,
) -> str:
    """
    Create a signed JWT for service-to-service auth.
    Used by products (QIAD, Wasla) to call AI Core.
    """
    secret = _get_product_secret(issuer) or _get_master_secret()
    if not secret:
        raise AuthError(f"No service secret configured for issuer: {issuer}")

    now = int(time.time())
    import uuid
    payload = {
        "iss": issuer,
        "aud": "ai-core",
        "sub": subject,
        "org": organization_id,
        "permissions": permissions,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)

    # Simple JWT: header.payload.signature (HS256)
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig_input = f"{header}.{body}"
    signature = hmac.new(secret.encode(), sig_input.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{header}.{body}.{sig_b64}"


def verify_service_token(token: str) -> dict:
    """
    Verify a service JWT and return its claims.
    Raises AuthError on any verification failure.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError("Malformed service token")

        header_b64, body_b64, sig_b64 = parts

        # Decode payload
        padding = 4 - len(body_b64) % 4
        body_padded = body_b64 + "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(body_padded))

        # Check expiry
        if payload.get("exp", 0) < time.time():
            raise AuthError("Service token expired")

        # Check audience
        if payload.get("aud") != "ai-core":
            raise AuthError("Invalid token audience")

        # Verify signature
        issuer = payload.get("iss", "")
        secret = _get_product_secret(issuer) or _get_master_secret()
        if not secret:
            raise AuthError(f"Unknown issuer: {issuer}")

        sig_input = f"{header_b64}.{body_b64}"
        expected_sig = hmac.new(secret.encode(), sig_input.encode(), hashlib.sha256).digest()
        actual_sig_padded = sig_b64 + "=" * (4 - len(sig_b64) % 4)
        actual_sig = base64.urlsafe_b64decode(actual_sig_padded)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise AuthError("Invalid service token signature")

        return payload

    except AuthError:
        raise
    except Exception as e:
        raise AuthError(f"Token verification failed: {e}")


def build_context_from_token(claims: dict) -> ExecutionContext:
    """
    Build an ExecutionContext from verified JWT claims.
    The tenant_id comes from the verified 'org' claim — NEVER from client input.
    """
    issuer = claims.get("iss", "")

    # Map issuer to product
    product_map = {
        "qiad": Product.QIAD,
        "wasla": Product.WASLA,
        "easy_delivery": Product.EASY_DELIVERY,
        "zawed": Product.ZAWED,
        "legacy_personal": Product.LEGACY_PERSONAL,
    }
    product = product_map.get(issuer)
    if product is None:
        raise AuthError(f"Unknown JWT issuer: {issuer}")

    return ExecutionContext(
        tenant_id=claims["org"],
        product=product,
        actor=Actor(
            type=ActorType.USER,
            id=claims["sub"],
            permissions=tuple(claims.get("permissions", [])),
        ),
        request_id=claims.get("jti", ""),
        agent_mode=AgentMode(claims.get("agent_mode", "copilot")),
        channel=claims.get("channel"),
        language=claims.get("language", "ar"),
    )
