from fastapi import APIRouter, Depends
from app.schemas.files import FileAnalyzeRequest, FileAnalyzeResponse
from app.agents import file_agent
from app.services import file_processor, audit_log
from app.routers._auth import require_scope

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/analyze-text", response_model=FileAnalyzeResponse)
async def analyze_text(req: FileAnalyzeRequest, _=Depends(require_scope("files:write"))):
    result = await file_agent.analyze_text(
        file_name=req.file_name,
        mime_type=req.mime_type,
        content=req.content,
        instruction=req.instruction,
    )
    artifact_id = await file_processor.save_artifact(
        task_id=req.task_id,
        file_name=req.file_name,
        mime_type=req.mime_type,
        summary=result["summary"],
        key_points=result["key_points"],
        actions=result["actions"],
        risk_notes=result["risk_notes"],
    )
    await audit_log.log_action(
        task_id=req.task_id, action="file_analyzed",
        payload={"artifact_id": artifact_id, "file": req.file_name}, status="ok",
    )
    return FileAnalyzeResponse(artifact_id=artifact_id, **result)
