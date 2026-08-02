"""
Email Agent — drafts email replies. NEVER sends. Returns draft only.
Sending requires explicit approval via /approvals endpoint.
"""
from app.agents import _openai_chat

SYSTEM = """
You are a senior professional email writer for Awab at EasyDelivery, a courier and e-commerce
fulfillment company in Saudi Arabia.

Your task: write a professional reply to the email provided.
Follow the instruction exactly.
Match the language of the instruction (Arabic → Arabic reply, English → English reply, auto → match original email).

RULES:
- Never invent facts, client names, order numbers, or amounts
- If information is missing, note it in risk_notes
- Always sign as: Awab | EasyDelivery Operations
- Do NOT send — only draft

Return structured text in this format:
SUMMARY: (one sentence what this email is about)
---
DRAFT:
(the full email body)
---
RISK_NOTES:
- (any concerns or missing info)
"""


async def draft(
    email_subject: str,
    email_body: str,
    instruction: str,
    language: str = "auto",
) -> dict:
    lang_note = f"\nLanguage preference: {language}" if language != "auto" else ""
    prompt = (
        f"Original Email Subject: {email_subject}\n"
        f"Original Email Body:\n{email_body}\n\n"
        f"Instruction: {instruction}{lang_note}"
    )
    raw = await _openai_chat(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=1000,
    )

    # Parse the structured text response
    summary = ""
    draft_reply = ""
    risk_notes: list[str] = []

    parts = raw.split("---")
    for part in parts:
        part = part.strip()
        if part.startswith("SUMMARY:"):
            summary = part.replace("SUMMARY:", "").strip()
        elif part.startswith("DRAFT:"):
            draft_reply = part.replace("DRAFT:", "").strip()
        elif part.startswith("RISK_NOTES:"):
            notes_text = part.replace("RISK_NOTES:", "").strip()
            risk_notes = [
                line.lstrip("- ").strip()
                for line in notes_text.splitlines()
                if line.strip() and line.strip() != "-"
            ]

    return {
        "summary": summary or raw[:200],
        "draft_reply": draft_reply or raw,
        "risk_notes": risk_notes,
        "needs_approval": True,
    }
