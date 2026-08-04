from fastapi import APIRouter, Depends
from app.schemas.olivery import (
    OliveryReportRequest, OliveryReportResponse,
    OliveryEditOrderRequest, OliveryEditOrderResponse,
)
from app.agents import olivery_agent
from app.services import audit_log, olivery_edit_store, olivery_report_store
from app.routers._auth import require_scope

router = APIRouter(prefix="/olivery", tags=["Olivery"])


@router.post("/report", response_model=OliveryReportResponse)
async def olivery_report(req: OliveryReportRequest, _=Depends(require_scope("olivery:read"))):
    result = await olivery_agent.report(
        report_type=req.report_type,
        filters=req.filters,
    )
    report_id = await olivery_report_store.save_report(
        task_id=req.task_id,
        report_type=result["report_type"],
        filters=result["filters"],
        summary=result["summary"],
        rows=result["rows"],
    )
    await audit_log.log_action(
        task_id=req.task_id, action="olivery_report",
        payload={"report_id": report_id, "report_type": req.report_type, "filters": req.filters}, status="ok",
    )
    return OliveryReportResponse(report_id=report_id, **result)


@router.post("/edit-order", response_model=OliveryEditOrderResponse)
async def olivery_edit_order(req: OliveryEditOrderRequest, _=Depends(require_scope("olivery:write"))):
    staged = await olivery_agent.stage_edit(order_id=req.order_id, vals=req.vals)
    request_id = await olivery_edit_store.save_edit_request(
        task_id=req.task_id, order_id=req.order_id, vals=req.vals, preview=staged["preview"],
    )
    await audit_log.log_action(
        task_id=req.task_id, action="olivery_edit_staged",
        payload={"request_id": request_id, "order_id": req.order_id, "vals": req.vals}, status="ok",
    )
    return OliveryEditOrderResponse(
        request_id=request_id, order_id=req.order_id, vals=req.vals, preview=staged["preview"],
    )
