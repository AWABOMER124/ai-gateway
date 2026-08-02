"""
Olivery Agent — generates operational reports using the Olivery/EasyDelivery API.
Gracefully degrades if credentials are missing from .env.
"""
import json
from app.agents import _openai_chat
from app.services.olivery_client import OliveryClient, OliveryNotConfigured

REPORT_SYSTEM = """
You are an operations analyst for EasyDelivery. Given raw order data from the Olivery API,
generate a clear, concise operational report in the same language as the instruction.

Format the report with:
- A one-paragraph executive summary
- Key metrics (total, delivered, pending, RTO, COD collected if available)
- Notable patterns or issues
- Recommended actions

Be factual. Use only the data provided. Never invent numbers.
"""

REPORT_TYPES = {
    "operation_daily": "Daily operations overview — all orders today",
    "delayed_shipments": "Orders that exceeded expected delivery time",
    "cod_summary": "Cash on delivery collection summary",
    "finance_settlement": "Settlement amounts owed or paid",
    "order_tracking": "Status of specific order IDs",
}


async def report(
    report_type: str,
    filters: dict,
) -> dict:
    if report_type not in REPORT_TYPES:
        return {
            "report_type": report_type,
            "filters": filters,
            "summary": f"Unknown report type '{report_type}'. Valid types: {list(REPORT_TYPES.keys())}",
            "rows": [],
            "needs_review": True,
        }

    try:
        client = OliveryClient()
        rows = await client.fetch(report_type=report_type, filters=filters)
    except OliveryNotConfigured as e:
        return {
            "report_type": report_type,
            "filters": filters,
            "summary": f"[Olivery not configured] {e}. Set OLIVERY_BASE_URL, OLIVERY_DB, OLIVERY_LOGIN, OLIVERY_PASSWORD in .env",
            "rows": [],
            "needs_review": True,
        }
    except Exception as e:
        return {
            "report_type": report_type,
            "filters": filters,
            "summary": f"[Olivery API error] {e}",
            "rows": [],
            "needs_review": True,
        }

    # Summarize with GPT
    data_preview = json.dumps(rows[:30], ensure_ascii=False)
    prompt = (
        f"Report Type: {report_type} — {REPORT_TYPES[report_type]}\n"
        f"Filters: {json.dumps(filters, ensure_ascii=False)}\n"
        f"Total rows: {len(rows)}\n"
        f"Sample data (first 30):\n{data_preview}"
    )
    summary = await _openai_chat(
        messages=[{"role": "system", "content": REPORT_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=700,
    )

    return {
        "report_type": report_type,
        "filters": filters,
        "summary": summary,
        "rows": rows,
        "needs_review": True,
    }


async def stage_edit(order_id: str, vals: dict) -> dict:
    """Builds a before/after preview for a proposed order edit. Never writes — staging only."""
    try:
        client = OliveryClient()
    except OliveryNotConfigured as e:
        return {"preview": f"[Olivery not configured] {e}", "current": {}}

    try:
        rows = await client.fetch("order_tracking", {"order_ids": [order_id]})
        current = rows[0] if rows else {}
    except Exception as e:
        current = {}
        changes_note = f"(تعذر جلب بيانات الطلب الحالية: {e})\n"
    else:
        changes_note = ""

    lines = [f"طلب #{order_id}:"]
    for field, new_value in vals.items():
        old_value = current.get(field, "غير معروف")
        lines.append(f"  {field}: {old_value} → {new_value}")
    preview = changes_note + "\n".join(lines)

    return {"preview": preview, "current": current}
