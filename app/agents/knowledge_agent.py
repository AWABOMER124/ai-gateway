"""
Knowledge Agent — answers questions using the RAG vector database.
Wraps the existing /search + /ask logic in agent form.
"""
import os
import asyncio
import psycopg2
import psycopg2.extras
from app.agents import _openai_chat

SYSTEM = """
You are Awab's AI Chief of Staff for EasyDelivery.
Answer the question using ONLY the context provided from the knowledge base.
If the answer is not in the context, say "I don't have this information in the knowledge base."
Be concise and practical. Respond in the same language as the question.
"""


def _vector_search(query_embedding: list[float], top_k: int = 6) -> list[dict]:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "awab_ai")
        user = os.getenv("POSTGRES_USER", "awab_ai")
        pw = os.getenv("POSTGRES_PASSWORD", "")
        db_url = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            cur.execute(
                """
                SELECT content, source_file, chunk_index,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM knowledge_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec_str, vec_str, top_k),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def _embed(text: str) -> list[float]:
    import httpx
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": text},
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


async def answer(question: str, top_k: int = 6) -> dict:
    embedding = await _embed(question)
    chunks = await asyncio.to_thread(_vector_search, embedding, top_k)

    if not chunks:
        return {
            "answer": "No relevant information found in the knowledge base.",
            "sources": [],
            "confidence": "low",
        }

    context = "\n\n---\n\n".join(
        f"[{c['source_file']}]\n{c['content']}" for c in chunks
    )
    prompt = f"Question: {question}\n\nKnowledge Base Context:\n{context}"
    answer_text = await _openai_chat(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=800,
    )

    return {
        "answer": answer_text,
        "sources": [{"file": c["source_file"], "similarity": round(c["similarity"], 3)} for c in chunks],
        "confidence": "high" if chunks[0]["similarity"] > 0.8 else "medium",
    }
