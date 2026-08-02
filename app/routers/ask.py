import time
import logging
from fastapi import APIRouter, HTTPException

from app.schemas.ask import AskRequest, AskResponse, SourceItem
from app.rag.search import search_chunks
from app.rag.answer import generate_answer
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/ask', response_model=AskResponse)
def ask_endpoint(req: AskRequest):
    """
    استقبال سؤال، البحث في قاعدة المعرفة، توليد إجابة بأسلوب أواب.

    الخطوات:
    1. vector search في ai_chunks
    2. بناء prompt من chunks + السؤال
    3. استدعاء OpenAI Chat
    4. إرجاع الإجابة + المصادر
    """
    t0 = time.time()

    # ─── 1. البحث ─────────────────────────────────────────────────────────────
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

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail='لم يُعثر على محتوى مناسب في قاعدة المعرفة. تأكد من تشغيل ingest_markdown.py أولاً.',
        )

    # ─── 2. توليد الإجابة ─────────────────────────────────────────────────────
    t1 = time.time()

    try:
        answer, tokens_used = generate_answer(
            question=  req.question,
            chunks=    chunks,
            task_type= req.task_type,
        )
    except (ValueError, EnvironmentError) as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception('خطأ في توليد الإجابة')
        raise HTTPException(status_code=500, detail=f'خطأ في توليد الإجابة: {e}')

    llm_ms = int((time.time() - t1) * 1000)

    # ─── 3. تجميع المصادر ─────────────────────────────────────────────────────
    sources: list[SourceItem] = []
    if req.show_sources:
        sources = [
            SourceItem(
                file_name=  c.get('file_name', ''),
                title=      c.get('title'),
                category=   c.get('category', ''),
                score=      float(c.get('score', 0)),
                chunk_text= c.get('chunk_text', ''),
            )
            for c in chunks
        ]

    return AskResponse(
        answer=      answer,
        sources=     sources,
        model=       settings.chat_model,
        tokens_used= tokens_used,
        search_ms=   search_ms,
        llm_ms=      llm_ms,
    )
