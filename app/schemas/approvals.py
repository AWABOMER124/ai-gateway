from pydantic import BaseModel
from typing import Any


class ApprovalDecision(BaseModel):
    task_id: str
    approved: bool
    note: str = ""


class PendingApproval(BaseModel):
    pending: bool
    task_id: str | None = None
    message: str | None = None
    intent: str | None = None


class ApprovalStatus(BaseModel):
    task_id: str
    status: str
    intent: str | None = None
    risk_level: str | None = None
    output: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
