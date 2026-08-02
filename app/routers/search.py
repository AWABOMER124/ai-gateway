import time
import logging
from fastapi import APIRouter, HTTPException

from app.schemas.search import SearchRequest, SearchResponse, ChunkResult
from app.rag.search import search_chunks

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/search', response_model=SearchResponse)
def search_endpoint(req: SearchRequest):
    """
    يبحث في ai_chunks ويرجع الـ chunks المناسبة بدون توليد إجابة.
    مفيد لاختبار جودة البحث أو لبناء pipeline مخصص.
    """
    t0 = time.time()

    try:
        chunks = search_chunks(
            question= req.question,
            top_k=    req.top_k,
            category= req.category,
            project=  req.project,
        )
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception('خطأ في البحث')
        raise HTTPException(status_code=500, detail=f'خطأ في البحث: {e}')

    search_ms = int((time.time() - t0) * 1000)

    results = [
        ChunkResult(
            id=             c.get('id', ''),
            file_name=      c.get('file_name', ''),
            title=          c.get('title'),
            category=       c.get('category', ''),
            folder=         c.get('folder', ''),
            score=          float(c.get('score', 0)),
            chunk_text=     c.get('chunk_text', ''),
            token_estimate= c.get('token_estimate'),
            metadata=       c.get('metadata'),
        )
        for c in chunks
    ]

    return SearchResponse(
        question=  req.question,
        results=   results,
        total=     len(results),
        search_ms= search_ms,
    )
