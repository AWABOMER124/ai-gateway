"""
Awab Personal AI Office — Agent Layer
All agents are stateless functions. State lives in task_store.
"""
import os
import json
import httpx
from typing import Any
from app.services import openai_usage


async def _openai_chat(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1200,
    json_mode: bool = False,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    model = model or os.getenv("CHAT_MODEL", "gpt-4.1-mini")

    await openai_usage.check_spend_cap()

    payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    usage = data.get("usage") or {}
    await openai_usage.record_usage(
        endpoint="chat",
        model=model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
    return data["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
