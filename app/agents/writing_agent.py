"""
Writing Agent — business proposals, contracts, announcements, SOPs.
All output is draft. Sending/sharing requires approval.
"""
from app.agents import _openai_chat

SYSTEM = """
You are a senior business writer for Awab at EasyDelivery, a courier and e-commerce
fulfillment company in Saudi Arabia.

Write professional business documents in Arabic or English as specified.
Follow the document type and any specific instructions provided.

For proposals: include executive summary, services offered, pricing table, terms, call-to-action.
For SOPs: include purpose, scope, steps, responsible parties, KPIs.
For announcements: formal, branded, clear.

Sign all external documents as: Awab | EasyDelivery | Operations Manager
Do NOT invent numbers or client details not given in the prompt.
"""

DOCUMENT_TYPES = [
    "proposal",
    "contract_summary",
    "sop",
    "announcement",
    "meeting_agenda",
    "report_narrative",
    "other",
]


async def write(
    document_type: str,
    instruction: str,
    context: str = "",
    language: str = "ar",
) -> dict:
    lang_note = "Write in Arabic." if language == "ar" else "Write in English."
    context_section = f"\n\nAdditional Context:\n{context}" if context else ""
    prompt = (
        f"Document Type: {document_type}\n"
        f"Language: {lang_note}\n"
        f"Instruction: {instruction}{context_section}"
    )
    content = await _openai_chat(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=1200,
    )
    return {
        "document_type": document_type,
        "language": language,
        "content": content,
        "needs_approval": True,
        "risk_notes": ["Review before sharing with external parties."],
    }
