from fastapi import APIRouter, Depends
from app.schemas.agent import PlanRequest, PlanResponse, ReviewRequest, ReviewResponse
from app.agents import supervisor, reviewer
from app.services import task_store, audit_log
from app.routers._auth import require_scope

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/plan", response_model=PlanResponse)
async def plan_endpoint(req: PlanRequest, _=Depends(require_scope("agent:write"))):
    plan = await supervisor.plan(
        message=req.message,
        channel=req.channel,
        user_id=req.user_id,
        context=req.context,
    )
    task_id = await task_store.create_task(
        user_id=req.user_id,
        channel=req.channel,
        message=req.message,
        plan=plan,
        channel_ref=req.channel_ref,
    )
    await audit_log.log_action(task_id=task_id, action="plan_created", payload=plan, status="ok")
    return PlanResponse(**plan, task_id=task_id)


@router.post("/review", response_model=ReviewResponse)
async def review_endpoint(req: ReviewRequest, _=Depends(require_scope("agent:write"))):
    result = await reviewer.review(
        task_id=req.task_id,
        original_request=req.original_request,
        agent_output=req.agent_output,
        agent_name=req.agent_name,
        risk_level=req.risk_level,
    )
    await task_store.save_review(task_id=req.task_id, review=result)
    if not result.get("approved"):
        status = "rejected"
    elif result.get("needs_user_confirmation"):
        status = "awaiting_confirmation"
    else:
        status = "completed"
    await task_store.update_task_status(task_id=req.task_id, status=status, output=result)
    await audit_log.log_action(task_id=req.task_id, action="review_completed", payload=result, status=status)
    return ReviewResponse(**result)
