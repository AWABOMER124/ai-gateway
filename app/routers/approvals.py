from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.approvals import ApprovalDecision, ApprovalStatus, PendingApproval
from app.services import task_store, audit_log, olivery_edit_store
from app.agents import executor
from app.routers._auth import require_api_key

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("/pending", response_model=PendingApproval)
async def get_pending(channel_ref: str = Query(...), _=Depends(require_api_key)):
    task = await task_store.get_pending_task(channel_ref)
    if not task:
        return PendingApproval(pending=False)
    return PendingApproval(
        pending=True,
        task_id=str(task["id"]),
        message=(task.get("output") or {}).get("final_answer", ""),
        intent=task.get("intent"),
    )


@router.get("/{task_id}", response_model=ApprovalStatus)
async def get_approval_status(task_id: str, _=Depends(require_api_key)):
    task = await task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return ApprovalStatus(
        task_id=task_id,
        status=task.get("status", "unknown"),
        intent=task.get("intent"),
        risk_level=task.get("risk_level"),
        output=task.get("output"),
    )


@router.post("/decide", response_model=ApprovalStatus)
async def decide(req: ApprovalDecision, _=Depends(require_api_key)):
    task = await task_store.get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id} not found")

    execution = None
    if req.approved:
        action_type = None
        assigned_agent = task.get("assigned_agent")
        if assigned_agent == "email_agent":
            action_type = "send_email"
        elif assigned_agent == "olivery_agent":
            edit_request = await olivery_edit_store.get_edit_request_by_task(req.task_id)
            if edit_request:
                action_type = "update_order_status"

        if action_type:
            execution = await executor.execute(task_id=req.task_id, action_type=action_type, payload={})
            new_status = "executed" if execution.get("success") else "execution_failed"
        else:
            new_status = "user_approved"
    else:
        new_status = "user_rejected"

    await task_store.update_task_status(
        task_id=req.task_id,
        status=new_status,
        output={"user_decision": req.approved, "note": req.note, "execution": execution},
    )
    await audit_log.log_action(
        task_id=req.task_id, action="user_decision",
        payload={"approved": req.approved, "note": req.note}, status=new_status,
    )
    return ApprovalStatus(
        task_id=req.task_id,
        status=new_status,
        intent=task.get("intent"),
        risk_level=task.get("risk_level"),
        execution=execution,
    )
