from pydantic import BaseModel
from typing import Any


class FileAnalyzeRequest(BaseModel):
    file_name: str
    mime_type: str = "text/plain"
    content: str
    instruction: str
    task_id: str | None = None


class ActionItem(BaseModel):
    action: str
    urgency: str = "medium"
    owner: str = "Awab"


class FileAnalyzeResponse(BaseModel):
    artifact_id: str | None = None
    summary: str
    key_points: list[str] = []
    actions: list[dict[str, Any]] = []
    risk_notes: list[str] = []
