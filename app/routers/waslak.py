from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.waslak import (
    StoreDraftGenerateRequest, StoreDraftGenerateResponse, StoreDraftStatusResponse,
    MerchantListResponse, MerchantInsightsResponse,
)
from app.agents import waslak_agent
from app.services import waslak_draft_store, waslak_insight_store, audit_log
from app.services.waslak_client import WaslakClient, WaslakNotConfigured, WaslakAPIError
from app.routers._auth import require_api_key

router = APIRouter(prefix="/waslak", tags=["Waslak"])


@router.post("/store-draft", response_model=StoreDraftGenerateResponse)
async def generate_store_draft(req: StoreDraftGenerateRequest, _=Depends(require_api_key)):
    payload = await waslak_agent.generate_store_draft(prompt=req.prompt, business_type=req.business_type)
    validation_errors = payload.pop("_validation_errors", [])
    local_id = await waslak_draft_store.save_draft(
        task_id=req.task_id, prompt=req.prompt, business_type=req.business_type,
        payload=payload, validation_errors=validation_errors,
    )
    await audit_log.log_action(
        task_id=req.task_id, action="waslak_draft_staged",
        payload={"local_id": local_id, "validation_errors": validation_errors}, status="ok",
    )
    return StoreDraftGenerateResponse(
        local_id=local_id, task_id=req.task_id, payload=payload, validation_errors=validation_errors,
    )


@router.get("/store-draft/{local_id}", response_model=StoreDraftStatusResponse)
async def get_store_draft_status(local_id: str, _=Depends(require_api_key)):
    draft = await waslak_draft_store.get_draft(local_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {local_id} not found")

    if draft.get("waslak_draft_id") and draft.get("waslak_status") == "PENDING":
        try:
            client = WaslakClient()
            remote = await client.get_draft(draft["waslak_draft_id"])
            await waslak_draft_store.update_remote_status(
                local_id=local_id, waslak_draft_id=draft["waslak_draft_id"],
                waslak_status=remote.get("status"), merchant_id=remote.get("merchantId"),
                rejection_reason=remote.get("rejectionReason"),
            )
            draft["waslak_status"] = remote.get("status")
            draft["merchant_id"] = remote.get("merchantId")
            draft["rejection_reason"] = remote.get("rejectionReason")
        except (WaslakNotConfigured, WaslakAPIError):
            pass  # degrade gracefully — show last known local state, don't fail the poll

    return StoreDraftStatusResponse(
        local_id=str(draft["id"]), approval_status=draft["approval_status"],
        validation_errors=draft.get("validation_errors") or [],
        waslak_draft_id=draft.get("waslak_draft_id"), waslak_status=draft.get("waslak_status"),
        merchant_id=draft.get("merchant_id"), rejection_reason=draft.get("rejection_reason"),
    )


@router.get("/merchants", response_model=MerchantListResponse)
async def list_merchants(_=Depends(require_api_key)):
    try:
        merchants = await WaslakClient().list_merchants()
    except WaslakNotConfigured as e:
        raise HTTPException(status_code=503, detail=f"Waslak not configured: {e}")
    except WaslakAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    await audit_log.log_action(
        task_id=None, action="waslak_merchants_listed", payload={"count": len(merchants)}, status="ok",
    )
    return MerchantListResponse(merchants=merchants)


@router.get("/merchants/{merchant_id}/insights", response_model=MerchantInsightsResponse)
async def merchant_insights(
    merchant_id: str,
    merchant_name: str = Query(""),
    task_id: str | None = Query(None),
    _=Depends(require_api_key),
):
    try:
        order_summary = await WaslakClient().get_merchant_orders(merchant_id)
    except WaslakNotConfigured as e:
        raise HTTPException(status_code=503, detail=f"Waslak not configured: {e}")
    except WaslakAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))

    suggestions = await waslak_agent.suggest_improvements(order_summary, merchant_name or merchant_id)
    insight_id = await waslak_insight_store.save_insight(
        task_id=task_id, merchant_id=merchant_id, order_summary=order_summary, suggestions=suggestions,
    )
    await audit_log.log_action(
        task_id=task_id, action="waslak_insights_generated",
        payload={"insight_id": insight_id, "merchant_id": merchant_id}, status="ok",
    )
    return MerchantInsightsResponse(
        insight_id=insight_id, merchant_id=merchant_id, order_summary=order_summary, suggestions=suggestions,
    )
