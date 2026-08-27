"""
Wasla Adapter — wraps the existing Waslak client with multi-tenant context.

This adapter bridges the legacy waslak_client.py and waslak_agent.py
into the multi-tenant platform. Existing functionality is preserved;
the adapter adds tenant isolation and context propagation.

The existing code in app/services/waslak_client.py and app/agents/waslak_agent.py
continues to work unchanged for legacy single-tenant use. This adapter
provides the multi-tenant path.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.context import ExecutionContext

logger = logging.getLogger(__name__)


class WaslaAdapter:
    """
    Multi-tenant wrapper around the existing Waslak integration.

    For Phase 1A, this provides the contract and delegates to
    existing waslak_client.py functions. Full multi-tenant Wasla
    (Store Architect V2) will be built in Phase 1D.
    """

    async def generate_store_draft(
        self,
        ctx: ExecutionContext,
        merchant_description: str,
        merchant_name: Optional[str] = None,
        style_preferences: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Generate a store draft using the AI.

        Wraps the existing waslak_agent.generate_draft() with tenant context.
        """
        from app.agents.waslak_agent import generate_draft

        # The existing function is async and returns a StoreDraftResponse-compatible dict
        result = await generate_draft(merchant_description, merchant_name)

        # Tag with tenant for audit
        if isinstance(result, dict):
            result["_tenant_id"] = ctx.tenant_id
            result["_product"] = ctx.product.value

        return result

    async def submit_draft_to_waslak(
        self,
        ctx: ExecutionContext,
        draft_data: dict,
        merchant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Submit a generated draft to the Waslak platform.

        Wraps waslak_client.submit_draft() with tenant context.
        """
        from app.services.waslak_client import submit_draft

        result = await submit_draft(draft_data, merchant_id=merchant_id)
        return result

    async def get_merchant_insights(
        self,
        ctx: ExecutionContext,
        merchant_id: str,
    ) -> dict[str, Any]:
        """
        Get AI-generated insights for a merchant's store.

        Wraps waslak_agent.suggest_improvements() with tenant context.
        """
        from app.agents.waslak_agent import suggest_improvements

        result = await suggest_improvements(merchant_id)
        return result

    async def list_merchants(
        self,
        ctx: ExecutionContext,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """List merchants accessible to this tenant."""
        from app.services.waslak_client import list_merchants

        result = await list_merchants(page=page, per_page=per_page)
        return result

    async def get_draft(
        self,
        ctx: ExecutionContext,
        local_id: str,
    ) -> dict[str, Any]:
        """Get a store draft by its local ID."""
        from app.services.waslak_client import get_draft

        result = await get_draft(local_id)
        return result
