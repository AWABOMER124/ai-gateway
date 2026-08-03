"""
rag/answer.py — توليد الإجابة النهائية عبر OpenAI Chat.
"""

import logging
from typing import Optional

from app.config import settings
from app.rag.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from app.services import openai_usage

logger = logging.getLogger(__name__)


def generate_answer(
    question:  str,
    chunks:    list[dict],
    task_type: Optional[str] = None,
) -> tuple[str, int]:
    """
    يستدعي OpenAI Chat API ويرجع (answer, tokens_used).

    يرفع استثناء واضح عند:
    - OPENAI_API_KEY غير صالح
    - تجاوز الـ rate limit
    - أي خطأ في API
    """
    if not settings.openai_api_key:
        raise EnvironmentError('OPENAI_API_KEY غير موجود في .env')

    openai_usage.check_spend_cap_sync()

    import openai
    client = openai.OpenAI(api_key=settings.openai_api_key)

    user_prompt = build_user_prompt(question, chunks, task_type)

    try:
        response = client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user',   'content': user_prompt},
            ],
            temperature=0.3,
        )
        answer = response.choices[0].message.content or ''
        usage = response.usage
        tokens = usage.total_tokens if usage else 0
        openai_usage.record_usage_sync(
            endpoint='chat',
            model=settings.chat_model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            total_tokens=tokens,
        )
        return answer, tokens

    except openai.AuthenticationError:
        raise ValueError('OPENAI_API_KEY غير صالح — تحقق من .env')

    except openai.RateLimitError:
        raise RuntimeError('تجاوزت حد الاستخدام — انتظر وحاول مجدداً')

    except openai.APIError as e:
        raise RuntimeError(f'OpenAI API error: {e}')
