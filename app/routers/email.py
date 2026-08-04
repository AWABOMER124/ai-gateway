from fastapi import APIRouter, Depends
from app.schemas.email import EmailDraftRequest, EmailDraftResponse
from app.agents import email_agent
from app.services import email_store, audit_log
from app.routers._auth import require_scope

router = APIRouter(prefix="/email", tags=["Email"])


@router.post("/draft", response_model=EmailDraftResponse)
async def draft_email(req: EmailDraftRequest, _=Depends(require_scope("email:write"))):
    result = await email_agent.draft(
        email_subject=req.email_subject,
        email_body=req.email_body,
        instruction=req.instruction,
        language=req.language,
    )
    draft_id = await email_store.save_draft(
        task_id=req.task_id,
        subject=req.email_subject,
        to_email=req.to_email,
        draft_body=result["draft_reply"],
        summary=result["summary"],
        risk_notes=result["risk_notes"],
    )
    await audit_log.log_action(
        task_id=req.task_id, action="email_draft_created",
        payload={"draft_id": draft_id, "to": req.to_email}, status="ok",
    )
    return EmailDraftResponse(draft_id=draft_id, **result)
