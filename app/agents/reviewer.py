"""
Reviewer Agent — quality-gates every agent output before it reaches the user.
Never modifies data. Returns approved/rejected + final_answer.
"""
from app.agents import _openai_chat, _parse_json

SYSTEM = """
You are the Quality Reviewer for Awab's AI Office at EasyDelivery.
Review the agent's output and decide if it is safe to send to Awab.

Rules:
- REJECT if the output contains hallucinated data (fake order numbers, fake emails, fake amounts)
- REJECT if the output proposes an irreversible action without explicit confirmation
- REJECT if risk_level is high and needs_user_confirmation has not been set
- FLAG needs_user_confirmation=true if the output will be sent externally (email, WhatsApp, etc.)
- Improve phrasing if needed but do NOT change facts or numbers
- Respond in the same language as the original_request

Return ONLY valid JSON:
{
  "approved": true|false,
  "final_answer": "clean output to send to Awab",
  "issues": ["issue1", "issue2"],
  "needs_user_confirmation": true|false
}
"""


async def review(
    task_id: str,
    original_request: str,
    agent_output: str,
    agent_name: str,
    risk_level: str,
) -> dict:
    prompt = (
        f"task_id: {task_id}\n"
        f"agent: {agent_name}\n"
        f"risk_level: {risk_level}\n"
        f"original_request: {original_request}\n\n"
        f"agent_output:\n{agent_output}"
    )
    raw = await _openai_chat(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=800,
    )
    result = _parse_json(raw)
    # high-risk always needs user confirmation
    if risk_level == "high":
        result["needs_user_confirmation"] = True
    return result
