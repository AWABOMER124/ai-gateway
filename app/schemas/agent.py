from pydantic import BaseModel
from typing import Any


class PlanRequest(BaseModel):
    message: str
    channel: str = "telegram"
    user_id: str = "awab"
    channel_ref: str = ""
    context: dict[str, Any] = {}


class PlanResponse(BaseModel):
    task_id: str
    intent: str
    assigned_agent: str
    risk_level: str
    needs_approval: bool
    missing_fields: list[str] = []
    extracted_fields: dict[str, Any] = {}
    plan: list[str] = []


class ReviewRequest(BaseModel):
    task_id: str
    original_request: str
    agent_output: str
    agent_name: str
    risk_level: str = "low"


class ReviewResponse(BaseModel):
    approved: bool
    final_answer: str
    issues: list[str] = []
    needs_user_confirmation: bool
