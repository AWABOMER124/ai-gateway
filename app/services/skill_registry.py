"""
Skill Registry — defines what "readiness" means for the 3 skill categories
surfaced on the dashboard's /dashboard/skills page: design, ecommerce, learning.

Two tiers per skill:
- health_check(): cheap, no GPT call — env vars present, modules importable,
  tables exist.
- capability_test(): a real task run through the actual agent/pipeline, with
  deterministic hard gates checked first (schema validity, non-empty
  retrieval, numeric sanity), then an LLM-judge call (via _openai_chat, so
  it's covered by the existing OpenAI spend cap) scoring the output 1-10
  against a fixed rubric. Pass = score >= 7 AND all hard gates green.

Callables here are side-effect-free (no DB writes) — app/routers/dashboard.py
persists results via app.services.skill_runs.record_run.
"""
import os
import asyncio
from app.agents import _openai_chat, _parse_json
from app.agents import waslak_agent
from app.services.db_pool import pooled_cursor

JUDGE_SYSTEM = """You are a strict QA grader. Score the given output 1-10 against the
rubric. Be critical — a generic or incoherent output should score low. Return ONLY
valid JSON: {"score": <1-10 integer>, "passed": <bool, true if score >= 7>, "reasons": "<one sentence>"}"""


async def _llm_judge(rubric: str, output_text: str) -> dict:
    raw = await _openai_chat(
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": f"Rubric:\n{rubric}\n\nOutput to grade:\n{output_text}"},
        ],
        json_mode=True,
        max_tokens=300,
    )
    return _parse_json(raw)


def _table_exists_and_nonempty_sync(table: str) -> bool:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT to_regclass(%s)", (table,))
        if cur.fetchone()["to_regclass"] is None:
            return False
        cur.execute(f"SELECT count(*) AS n FROM {table} LIMIT 1")
        return cur.fetchone()["n"] > 0


# ── design ──────────────────────────────────────────────────────────────

DESIGN_TEST_PROMPT = (
    "A cozy neighborhood coffee shop called 'Sunrise Beans' selling coffee, "
    "pastries, and simple breakfast items."
)


async def _health_design() -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        return {"passed": False, "summary": "OPENAI_API_KEY not set"}
    try:
        import app.agents.waslak_agent  # noqa: F401
    except Exception as e:
        return {"passed": False, "summary": f"waslak_agent not importable: {e}"}
    return {"passed": True, "summary": "OPENAI_API_KEY set, waslak_agent importable"}


async def _capability_design() -> dict:
    payload = await waslak_agent.generate_store_draft(DESIGN_TEST_PROMPT, "restaurant")
    errors = payload.get("_validation_errors") or []
    if errors:
        return {
            "passed": False, "score": None,
            "summary": f"Local schema validation failed: {errors}",
            "output_excerpt": str(payload),
        }
    rubric = (
        "Does the combination of name, slogan, welcomeText, and primaryColor form a "
        "coherent, non-generic brand identity matching the brief (a cozy neighborhood "
        "coffee shop called 'Sunrise Beans')?"
    )
    judged = await _llm_judge(rubric, str({k: payload.get(k) for k in ("name", "description", "slogan", "primaryColor", "welcomeText")}))
    return {
        "passed": bool(judged.get("passed")), "score": judged.get("score"),
        "summary": judged.get("reasons", ""), "output_excerpt": str(payload),
    }


# ── ecommerce ───────────────────────────────────────────────────────────

ECOMMERCE_TEST_PROMPT = (
    "A 3-category grocery store — Fruits, Dairy, Bakery — each with at least "
    "3 realistically priced products in EGP."
)


async def _health_ecommerce() -> dict:
    return await _health_design()  # same underlying agent/dependency


async def _capability_ecommerce() -> dict:
    payload = await waslak_agent.generate_store_draft(ECOMMERCE_TEST_PROMPT, "grocery")
    errors = list(payload.get("_validation_errors") or [])
    categories = payload.get("categories") or []
    if len(categories) < 3:
        errors.append(f"expected >=3 categories, got {len(categories)}")
    for c in categories:
        products = c.get("products") or []
        if len(products) < 3:
            errors.append(f"category '{c.get('name')}' has <3 products")
        for p in products:
            price = p.get("price")
            if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0 or price > 100000:
                errors.append(f"product '{p.get('name')}' has an implausible price: {price}")
    if errors:
        return {
            "passed": False, "score": None,
            "summary": f"Hard gate failed: {errors}",
            "output_excerpt": str(payload),
        }
    rubric = "Are the product names and prices realistic and internally consistent for a grocery store in Egypt?"
    judged = await _llm_judge(rubric, str(categories))
    return {
        "passed": bool(judged.get("passed")), "score": judged.get("score"),
        "summary": judged.get("reasons", ""), "output_excerpt": str(payload),
    }


# ── learning (RAG knowledge base) ──────────────────────────────────────

KNOWLEDGE_QA_FIXTURES = [
    {
        "question": "متى يطلب الوكيل موافقة صريحة؟",
        "expected_keywords": ["بيانات حقيقية", "مالي", "عميل", "بنية تحتية"],
    },
    {
        "question": "شنو المكونات الرئيسية لنظام تشغيل بلس؟",
        "expected_keywords": ["إدارة الطلبات", "المخزون", "الشحن", "CRM"],
    },
    {
        "question": "كيف يتعامل الوكيل مع نقص البيانات؟",
        "expected_keywords": ["لا يخترع", "الافتراضات", "يطلب"],
    },
]


async def _health_learning() -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        return {"passed": False, "summary": "OPENAI_API_KEY not set"}
    try:
        import app.rag.search  # noqa: F401
        import app.rag.answer  # noqa: F401
    except Exception as e:
        return {"passed": False, "summary": f"RAG modules not importable: {e}"}
    try:
        nonempty = await asyncio.to_thread(_table_exists_and_nonempty_sync, "ai_chunks")
    except Exception as e:
        return {"passed": False, "summary": f"ai_chunks check failed: {e}"}
    if not nonempty:
        return {"passed": False, "summary": "ai_chunks table missing or empty"}
    return {"passed": True, "summary": "OPENAI_API_KEY set, RAG modules importable, ai_chunks populated"}


async def _capability_learning() -> dict:
    from app.rag.search import search_chunks
    from app.rag.answer import generate_answer

    results = []
    for fx in KNOWLEDGE_QA_FIXTURES:
        chunks = await asyncio.to_thread(search_chunks, fx["question"], 6, None, None)
        if not chunks:
            results.append({"question": fx["question"], "passed": False, "score": 0, "reasons": "no chunks retrieved"})
            continue
        answer, _tokens = await asyncio.to_thread(generate_answer, fx["question"], chunks, None)
        rubric = (
            f"Does the answer correctly use the retrieved context and touch on these "
            f"expected points: {fx['expected_keywords']}?"
        )
        judged = await _llm_judge(rubric, answer)
        results.append({"question": fx["question"], **judged})

    passed = all(r.get("passed") for r in results)
    scores = [r.get("score") for r in results if isinstance(r.get("score"), (int, float))]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    summary = f"{sum(1 for r in results if r.get('passed'))}/{len(results)} fixtures passed"
    return {"passed": passed, "score": avg_score, "summary": summary, "output_excerpt": str(results)}


SKILLS = {
    "design": {
        "label": "Design",
        "health_check": _health_design,
        "capability_test": _capability_design,
    },
    "ecommerce": {
        "label": "E-commerce",
        "health_check": _health_ecommerce,
        "capability_test": _capability_ecommerce,
    },
    "learning": {
        "label": "Learning (Knowledge Base)",
        "health_check": _health_learning,
        "capability_test": _capability_learning,
    },
}
