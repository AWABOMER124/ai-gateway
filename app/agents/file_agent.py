"""
File Agent — analyzes pre-extracted text/JSON from n8n.
Does NOT handle binary files. n8n extracts content first, then sends text here.
"""
from app.agents import _openai_chat, _parse_json

SYSTEM = """
You are a document analyst for Awab at EasyDelivery.
Analyze the document content and provide a structured analysis.

Return ONLY valid JSON:
{
  "summary": "2-3 sentence overview of what this document is",
  "key_points": ["point 1", "point 2", "..."],
  "actions": [
    {"action": "what to do", "urgency": "high|medium|low", "owner": "Awab|system|team"}
  ],
  "risk_notes": ["anything suspicious, missing, or needing attention"]
}

Be factual. Extract from the content only. Never invent data.
If content is an Excel/CSV table, summarize statistics and notable rows.
If content is an email or PDF, summarize the ask and required response.
"""


async def analyze_text(
    file_name: str,
    mime_type: str,
    content: str,
    instruction: str,
) -> dict:
    content_preview = content[:4000] if len(content) > 4000 else content
    prompt = (
        f"File: {file_name} ({mime_type})\n"
        f"Instruction: {instruction}\n\n"
        f"Content:\n{content_preview}"
    )
    if len(content) > 4000:
        prompt += f"\n\n[Content truncated. Total length: {len(content)} chars]"

    raw = await _openai_chat(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=1000,
    )
    result = _parse_json(raw)

    # Ensure structure
    result.setdefault("summary", "")
    result.setdefault("key_points", [])
    result.setdefault("actions", [])
    result.setdefault("risk_notes", [])
    return result
