from pydantic import BaseModel


class EmailDraftRequest(BaseModel):
    email_subject: str = ""
    email_body: str
    instruction: str
    language: str = "auto"
    to_email: str = ""
    task_id: str | None = None


class EmailDraftResponse(BaseModel):
    draft_id: str | None = None
    summary: str
    draft_reply: str
    risk_notes: list[str] = []
    needs_approval: bool = True
