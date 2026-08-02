"""
rag/embeddings.py — توليد embedding vector لنص واحد.
"""

import time
import logging
from app.config import settings

logger = logging.getLogger(__name__)

_MAX_CHARS   = 8191 * 4   # حد تقريبي لـ text-embedding-3-small
_MAX_RETRIES = 3


def get_embedding(text: str) -> list[float]:
    """
    يحوّل النص إلى embedding vector باستخدام OpenAI.

    يرفع استثناء إذا:
    - OPENAI_API_KEY غير موجود
    - فشل API بعد كل المحاولات
    """
    if not text or not text.strip():
        raise ValueError('النص فارغ — لا يمكن توليد embedding')

    if not settings.openai_api_key:
        raise EnvironmentError('OPENAI_API_KEY غير موجود في .env')

    import openai
    client = openai.OpenAI(api_key=settings.openai_api_key)

    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS]

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.embeddings.create(
                model=settings.embedding_model,
                input=text,
                encoding_format='float',
            )
            return response.data[0].embedding

        except openai.RateLimitError:
            if attempt < _MAX_RETRIES - 1:
                wait = 2.0 * (2 ** attempt)
                logger.warning(f'Rate limit — انتظر {wait}s')
                time.sleep(wait)
            else:
                raise

        except openai.APIError:
            raise

    raise RuntimeError('فشل توليد embedding بعد كل المحاولات')
