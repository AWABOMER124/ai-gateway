from pydantic import BaseModel
from typing import Any


class StoreDraftGenerateRequest(BaseModel):
    task_id: str | None = None
    prompt: str
    business_type: str | None = None  # framing only: "ecommerce"|"restaurant"|"landing_page"


class StoreDraftGenerateResponse(BaseModel):
    local_id: str
    task_id: str | None = None
    payload: dict[str, Any]
    validation_errors: list[str] = []
    needs_approval: bool = True


class StoreDraftStatusResponse(BaseModel):
    local_id: str
    approval_status: str
    validation_errors: list[str] = []
    waslak_draft_id: str | None = None
    waslak_status: str | None = None
    merchant_id: str | None = None
    rejection_reason: str | None = None


class MerchantListResponse(BaseModel):
    merchants: list[dict[str, Any]]


class MerchantInsightsResponse(BaseModel):
    insight_id: str | None = None
    merchant_id: str
    order_summary: dict[str, Any]
    suggestions: str
