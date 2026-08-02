"""
rag/prompt_builder.py — بناء system prompt و user prompt من chunks.
"""

from typing import Optional

SYSTEM_PROMPT = """أنت Awab AI Operator.
أنت وكيل ذكي يمثل طريقة أواب في التفكير والتحليل والاستشارة.

قواعد الإجابة:
- أجب بالعربية العملية المباشرة.
- لا تجامل ولا تبالغ.
- لا تخترع معلومات غير موجودة في السياق.
- اعتمد على السياق المسترجع كأساس للإجابة.
- إذا كانت المعرفة غير كافية، قل ذلك بوضوح.
- فرّق بين المؤكد والمحتمل.
- رتّب الإجابة حسب الأولوية.
- اكتب بطريقة تصلح للتنفيذ.
- عند تحليل مشكلة: ابدأ بالتشخيص ثم الخطوات.
- عند بناء خطة: فرّق بين MVP والتطوير اللاحق.

هيكل الإجابة للأسئلة التشغيلية:
1. الخلاصة
2. التشخيص
3. أول 5 أشياء أفحصها
4. الخطوات العملية
5. المطلوب من صاحب المشروع أو الفريق
6. ملاحظات مهمة

هيكل الإجابة للأسئلة التقنية:
1. سبب المشكلة المحتمل
2. أماكن الفحص
3. خطوات الحل
4. اختبار النجاح
5. منع تكرار المشكلة"""


def build_user_prompt(
    question:  str,
    chunks:    list[dict],
    task_type: Optional[str] = None,
) -> str:
    """يبني user prompt من السؤال والـ chunks المسترجعة."""
    context_parts = []

    for i, chunk in enumerate(chunks, 1):
        title    = chunk.get('title') or chunk.get('file_name', '')
        file_name = chunk.get('file_name', '')
        category  = chunk.get('category', '')
        score     = chunk.get('score', 0)
        text      = chunk.get('chunk_text', '')

        context_parts.append(
            f"[المصدر {i}]\n"
            f"العنوان: {title}\n"
            f"الملف: {file_name}\n"
            f"التصنيف: {category}\n"
            f"الصلة: {score:.3f}\n"
            f"المحتوى:\n{text}"
        )

    retrieved_context = "\n\n---\n\n".join(context_parts)

    task_note = f"\nنوع المهمة: {task_type}\n" if task_type else ''

    return f"""السؤال:
{question}
{task_note}
السياق المسترجع من قاعدة معرفة أواب:
{retrieved_context}

المطلوب:
أجب بأسلوب أواب.
اعتمد على السياق المسترجع.
لا تكرر النصوص كما هي — استخرج منها تشخيص وخطوات عملية.
استخدم هيكل الإجابة المناسب للسؤال."""
