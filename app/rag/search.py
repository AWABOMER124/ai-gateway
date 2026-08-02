"""
rag/search.py — البحث في ai_chunks بـ vector similarity.
"""

import json
import logging
from typing import Optional

from app.config import settings
from app.database import db_cursor
from app.rag.embeddings import get_embedding

logger = logging.getLogger(__name__)


def search_chunks(
    question:  str,
    top_k:     int            = 6,
    category:  Optional[str]  = None,
    project:   Optional[str]  = None,
) -> list[dict]:
    """
    يسترجع أكثر chunks صلة بالسؤال.

    المنطق:
    1. يولّد embedding للسؤال.
    2. يبحث بـ cosine similarity في ai_chunks.
    3. يصفّي حسب category / project إن طُلب.
    4. يرجع نتائج مرتبة تنازلياً حسب score.

    المخرجات: list[dict] كل dict يحتوي:
      title, file_name, category, score, chunk_text, metadata
    """
    if not top_k or top_k < 1:
        top_k = settings.default_top_k

    q_embedding = get_embedding(question)
    emb_str = '[' + ','.join(str(v) for v in q_embedding) + ']'

    # بناء الشروط ديناميكياً
    conditions: list[str] = ['embedding IS NOT NULL']
    params: list = []

    if category:
        conditions.append('category = %s')
        params.append(category)

    if project:
        conditions.append("metadata->>'project' = %s")
        params.append(project)

    where_clause = ' AND '.join(conditions)

    sql = f"""
        WITH ranked AS (
            SELECT
                id,
                document_id,
                chunk_index,
                file_name,
                folder,
                category,
                title,
                chunk_text,
                token_estimate,
                metadata,
                1 - (embedding <=> %s::vector) AS score
            FROM ai_chunks
            WHERE {where_clause}
        )
        SELECT * FROM ranked
        WHERE score >= 0.30
        ORDER BY score DESC
        LIMIT %s
    """

    full_params = [emb_str] + params + [top_k]

    with db_cursor() as cur:
        cur.execute(sql, full_params)
        rows = cur.fetchall()

    results = []
    for row in rows:
        r = dict(row)
        # psycopg2 RealDictCursor يرجع metadata كـ dict مباشرة
        if isinstance(r.get('metadata'), str):
            r['metadata'] = json.loads(r['metadata'])
        # UUID → string
        r['id'] = str(r.get('id', ''))
        r['document_id'] = str(r.get('document_id', ''))
        results.append(r)

    return results
