"""
Executor — runs approved actions after user confirmation.
ONLY called when approval_status = 'approved' in the task store.
Each action type is gated separately.
"""
import os
import aiosmtplib
from email.message import EmailMessage
from app.services.audit_log import log_action
from app.services import email_store, olivery_edit_store, waslak_draft_store
from app.services.olivery_client import OliveryClient, OliveryNotConfigured
from app.services.waslak_client import (
    WaslakClient, WaslakNotConfigured, WaslakAPIError, WaslakRateLimited, WaslakValidationError,
)


ALLOWED_ACTIONS = {
    "send_email",
    "update_order_status",
    "mark_email_read",
    "save_draft",
    "submit_waslak_draft",
}


async def execute(task_id: str, action_type: str, payload: dict) -> dict:
    if action_type not in ALLOWED_ACTIONS:
        return {
            "success": False,
            "error": f"Unknown action '{action_type}'. Allowed: {list(ALLOWED_ACTIONS)}",
        }

    await log_action(task_id=task_id, action=action_type, payload=payload, status="attempted")

    if action_type == "send_email":
        return await _send_email(task_id, payload)
    if action_type == "update_order_status":
        return await _update_order_status(task_id, payload)
    if action_type == "mark_email_read":
        return {"success": False, "error": "Not implemented yet. Requires IMAP write access."}
    if action_type == "save_draft":
        return {"success": True, "message": "Draft saved to task store."}
    if action_type == "submit_waslak_draft":
        return await _submit_waslak_draft(task_id, payload)

    return {"success": False, "error": "Executor routing error."}


async def _send_email(task_id: str, payload: dict) -> dict:
    smtp_host = os.getenv("SMTP_HOST", "")
    if not smtp_host:
        return {
            "success": False,
            "error": "SMTP not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD in .env",
        }

    draft_id = payload.get("draft_id")
    draft = await email_store.get_draft(draft_id) if draft_id else await email_store.get_draft_by_task(task_id)
    if not draft:
        return {"success": False, "error": "No email draft found for this task."}
    if not draft.get("to_email"):
        return {"success": False, "error": "Draft has no recipient (to_email). Cannot send."}

    smtp_from = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = draft["to_email"]
    msg["Subject"] = draft.get("subject") or "(no subject)"
    msg.set_content(draft["draft_body"])

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=int(os.getenv("SMTP_PORT", "587")),
            username=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            start_tls=True,
        )
    except Exception as e:
        await log_action(task_id=task_id, action="send_email", payload=payload, status=f"failed: {e}")
        return {"success": False, "error": f"SMTP send failed: {e}"}

    await email_store.approve_draft(draft["id"])
    await log_action(task_id=task_id, action="send_email", payload={"draft_id": draft["id"]}, status="sent")
    return {"success": True, "message": f"Email sent to {draft['to_email']}."}


async def _update_order_status(task_id: str, payload: dict) -> dict:
    edit_request = await olivery_edit_store.get_edit_request_by_task(task_id)
    if not edit_request:
        return {"success": False, "error": "No staged Olivery edit found for this task."}

    try:
        client = OliveryClient()
    except OliveryNotConfigured as e:
        return {"success": False, "error": f"Olivery not configured: {e}"}

    try:
        result = await client.edit_order(edit_request["order_id"], edit_request["vals"])
    except Exception as e:
        await log_action(task_id=task_id, action="update_order_status", payload=payload, status=f"failed: {e}")
        return {"success": False, "error": f"Olivery edit_order failed: {e}"}

    await olivery_edit_store.mark_executed(edit_request["id"])
    await log_action(
        task_id=task_id, action="update_order_status",
        payload={"order_id": edit_request["order_id"], "vals": edit_request["vals"]}, status="executed",
    )
    return {"success": True, "message": f"Order {edit_request['order_id']} updated.", "result": result}


async def _submit_waslak_draft(task_id: str, payload: dict) -> dict:
    draft = await waslak_draft_store.get_draft_by_task(task_id)
    if not draft:
        return {"success": False, "error": "No staged Waslak store draft found for this task."}

    validation_errors = draft.get("validation_errors") or []
    if validation_errors:
        return {
            "success": False,
            "error": f"Draft failed local validation, refusing to submit: {validation_errors}",
        }

    try:
        client = WaslakClient()
    except WaslakNotConfigured as e:
        return {"success": False, "error": f"Waslak not configured: {e}"}

    submit_payload = dict(draft["payload"])
    submit_payload["prompt"] = draft["prompt"]

    try:
        result = await client.submit_draft(submit_payload)
    except WaslakRateLimited as e:
        await log_action(task_id=task_id, action="submit_waslak_draft", payload=payload, status=f"rate_limited: {e}")
        return {"success": False, "error": f"Waslak rate limit hit (30/hour): {e}"}
    except WaslakValidationError as e:
        await log_action(task_id=task_id, action="submit_waslak_draft", payload=payload, status=f"validation_failed: {e}")
        return {"success": False, "error": f"Waslak rejected draft (422): {e}"}
    except WaslakAPIError as e:
        await log_action(task_id=task_id, action="submit_waslak_draft", payload=payload, status=f"failed: {e}")
        return {"success": False, "error": f"Waslak submit failed: {e}"}

    await waslak_draft_store.update_remote_status(
        local_id=draft["id"], waslak_draft_id=result.get("id"),
        waslak_status=result.get("status", "PENDING"), merchant_id=None, rejection_reason=None,
        approval_status="executed",
    )
    await log_action(
        task_id=task_id, action="submit_waslak_draft",
        payload={"local_id": str(draft["id"]), "waslak_draft_id": result.get("id")}, status="executed",
    )
    return {
        "success": True,
        "message": f"Store draft submitted to Waslak (id={result.get('id')}, status={result.get('status')}).",
        "result": result,
    }
