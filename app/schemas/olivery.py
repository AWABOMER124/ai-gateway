from pydantic import BaseModel
from typing import Any


class OliveryReportRequest(BaseModel):
    report_type: str
    filters: dict[str, Any] = {}


class OliveryReportResponse(BaseModel):
    report_type: str
    filters: dict[str, Any]
    summary: str
    rows: list[dict[str, Any]] = []
    needs_review: bool = True


class OliveryEditOrderRequest(BaseModel):
    task_id: str | None = None
    order_id: str
    vals: dict[str, Any]


class OliveryEditOrderResponse(BaseModel):
    request_id: str
    order_id: str
    vals: dict[str, Any]
    preview: str
    needs_approval: bool = True
