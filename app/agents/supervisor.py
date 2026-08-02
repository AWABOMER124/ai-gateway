"""
Supervisor Agent — reads user intent, assigns agent, assesses risk.
Never executes actions itself. Only plans.
"""
from app.agents import _openai_chat, _parse_json

SYSTEM = """
You are the Supervisor AI for Awab's Personal AI Office at EasyDelivery.
Analyze the user request and return a structured JSON plan.

INTENTS:
- email_draft: user wants to write or reply to an email
- email_summary: user wants to read/summarize emails
- olivery_report: user wants any operational report (orders, COD, delayed, finance)
- olivery_edit_order: user wants to change something on an existing order (status, address, COD amount, etc.) — always risk_level high, and missing_fields must list "order_id" and/or the specific field(s) to change if not given
- file_analysis: user wants to analyze an uploaded file (Excel, PDF, image)
- knowledge_question: user asks a factual question answerable from the knowledge base
- proposal: user wants a price proposal or business document
- general: anything else (greet, brainstorm, advice)

RISK LEVELS:
- low: read-only, informational, drafts that won't be sent
- medium: draft for external communication, reports with sensitive data
- high: anything that could trigger real money movement, email sends, data changes

MISSING FIELDS: list any info needed but absent (e.g. recipient_email, report_date_range)

EXTRACTED FIELDS: pull structured values directly out of the user's message where possible, into "extracted_fields":
- to_email: recipient email address (for email_draft) — only if an actual address appears in the message
- order_id: order/AWB/tracking number (for olivery_edit_order or order_tracking)
- vals: object of order fields to change and their new values (for olivery_edit_order only), e.g. {"state": "delivered"}
Omit any key you cannot confidently extract — list it in missing_fields instead of guessing.

Return ONLY valid JSON:
{
  "intent": "...",
  "assigned_agent": "email_agent|olivery_agent|file_agent|knowledge_agent|writing_agent|general",
  "risk_level": "low|medium|high",
  "needs_approval": true|false,
  "missing_fields": [],
  "extracted_fields": {},
  "plan": ["step 1", "step 2"]
}
"""


async def plan(message: str, channel: str, user_id: str, context: dict) -> dict:
    ctx_str = ""
    if context:
        import json
        ctx_str = f"\nContext: {json.dumps(context, ensure_ascii=False)[:500]}"
    prompt = f"Channel: {channel}\nUser: {user_id}\nMessage: {message}{ctx_str}"
    raw = await _openai_chat(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=600,
    )
    result = _parse_json(raw)
    result.setdefault("extracted_fields", {})
    # needs_approval always true for medium/high risk
    if result.get("risk_level") in ("medium", "high"):
        result["needs_approval"] = True
    return result
