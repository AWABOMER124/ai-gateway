# Awab Personal AI Office

طبقة Multi-Agent فوق ai-gateway تحول RAG API بسيط إلى مكتب ذكي كامل.

---

## الفكرة

```
Telegram / n8n
      ↓
POST /agent/plan          ← Supervisor: يفهم الطلب ويخطط
      ↓
agent يُستدعى مباشرة     ← email_agent / olivery_agent / file_agent / ...
      ↓
POST /agent/review        ← Reviewer: يفحص الناتج قبل الإرسال
      ↓
إذا needs_approval → GET /approvals/{task_id}  ← أواب يقرر
      ↓
POST /approvals/decide    ← تنفيذ أو رفض
```

---

## الـ Agents

| Agent | الوظيفة | الـ Endpoint |
|-------|---------|-------------|
| **Supervisor** | يفهم الطلب، يصنّف النية، يقيّم الخطر | `POST /agent/plan` |
| **Reviewer** | يفحص ناتج أي agent قبل إرساله | `POST /agent/review` |
| **Email Agent** | يكتب رد احترافي على أي إيميل — لا يرسل أبداً | `POST /email/draft` |
| **Olivery Agent** | تقارير تشغيلية: يومية، متأخرة، COD، تسوية | `POST /olivery/report` |
| **File Agent** | يحلل نص مستخرج (Excel، PDF، صورة) | `POST /files/analyze-text` |
| **Knowledge Agent** | يجيب من RAG vector database | يُستدعى داخلياً |
| **Writing Agent** | يكتب عروض أسعار ووثائق أعمال | يُستدعى داخلياً |
| **Waslak Agent** | يولّد مسودة متجر/منيو/صفحة هبوط (Waslak StoreDraft)، وتحليلات/اقتراحات تحسين من إحصاءات التاجر | `POST /waslak/store-draft`, `GET /waslak/merchants/{id}/insights` |
| **Executor** | ينفذ الإجراءات بعد الموافقة فقط | يُستدعى من /approvals |

---

## الـ Endpoints

### Security
جميع الـ endpoints (ما عدا `/health`) تحتاج:
```
X-API-Key: <GATEWAY_API_KEY>
```

---

### POST /agent/plan

```bash
curl -X POST http://72.62.41.242:8000/agent/plan \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "اكتب رد على إيميل Red Bull عن تقرير الشحنات",
    "channel": "telegram",
    "user_id": "awab"
  }'
```

Response:
```json
{
  "intent": "email_draft",
  "assigned_agent": "email_agent",
  "risk_level": "medium",
  "needs_approval": true,
  "missing_fields": ["email_body"],
  "plan": ["Draft professional reply to Red Bull", "Review before sending"]
}
```

---

### POST /agent/review

```bash
curl -X POST http://72.62.41.242:8000/agent/review \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "uuid-here",
    "original_request": "اكتب رد على Red Bull",
    "agent_output": "Dear Red Bull team...",
    "agent_name": "email_agent",
    "risk_level": "medium"
  }'
```

Response:
```json
{
  "approved": true,
  "final_answer": "Dear Red Bull team...",
  "issues": [],
  "needs_user_confirmation": true
}
```

---

### POST /email/draft

```bash
curl -X POST http://72.62.41.242:8000/email/draft \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "email_subject": "Shipment Status Report - June 2026",
    "email_body": "Hi, can you provide an update on the 500 shipments sent last week?",
    "instruction": "Reply professionally confirming we will send the report within 2 hours",
    "language": "en",
    "to_email": "ops@redbull.com"
  }'
```

Response:
```json
{
  "draft_id": "uuid",
  "summary": "Reply to Red Bull requesting shipment status update",
  "draft_reply": "Dear Red Bull Operations Team,\n\nThank you for reaching out...",
  "risk_notes": [],
  "needs_approval": true
}
```

---

### POST /olivery/report

```bash
curl -X POST http://72.62.41.242:8000/olivery/report \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "operation_daily",
    "filters": {"date": "2026-06-30"}
  }'
```

Report types: `operation_daily` | `delayed_shipments` | `cod_summary` | `finance_settlement` | `order_tracking`

---

### POST /files/analyze-text

```bash
curl -X POST http://72.62.41.242:8000/files/analyze-text \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "file_name": "redbull_shipments_june.xlsx",
    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "content": "AWB,Status,Customer\n38500,Delivered,Ahmed\n38501,RTO,Sara",
    "instruction": "Summarize delivery performance and flag RTOs"
  }'
```

Response:
```json
{
  "artifact_id": "uuid",
  "summary": "Excel contains 2 shipments. 1 delivered, 1 RTO.",
  "key_points": ["50% RTO rate is high", "Sara's order needs follow-up"],
  "actions": [{"action": "Contact Sara about RTO", "urgency": "high", "owner": "Awab"}],
  "risk_notes": ["RTO rate above normal threshold"]
}
```

---

### POST /waslak/store-draft

يولّد مسودة متجر كاملة (اسم، وصف، فئات ومنتجات) من وصف نصي حر ويخزّنها محلياً بانتظار
الموافقة. **لا يرسل شيئاً لواصلك بهذه الخطوة** — الإرسال الفعلي (`POST
/api/agent/v1/stores/drafts` على واصلك) يصير فقط من الـ Executor بعد موافقة أواب عبر
`POST /approvals/decide`، بنفس منطق `email_draft`/`olivery_edit_order`.

```bash
curl -X POST http://72.62.41.242:8000/waslak/store-draft \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "uuid-here",
    "prompt": "مطعم برجر صغير في جدة، عندنا برجر لحم وبرجر دجاج ومشروبات",
    "business_type": "restaurant"
  }'
```

Response:
```json
{
  "local_id": "uuid",
  "task_id": "uuid-here",
  "payload": {"name": "...", "categories": [...]},
  "validation_errors": [],
  "needs_approval": true
}
```

`business_type` (`ecommerce`|`restaurant`|`landing_page`) تُستخدم فقط لتوجيه GPT — لا
تُرسل لواصلك (لا وجود لهذا الحقل بمخطط `StoreDraft` عندهم). `validation_errors` غير
فارغة تمنع الـ Executor من الإرسال حتى لو تمت الموافقة (يوفّر استهلاك حد الـ 30
مسودة/ساعة على مسودة مضمون رفضها).

---

### GET /waslak/store-draft/{local_id}

يرجّع حالة المسودة المحلية، ولو كانت مُرسَلة فعلياً لواصلك وحالتها لسه `PENDING`، يستقصي
(poll) حالتها الحقيقية من واصلك ويحدّث السجل المحلي — **واصلك ما عنده webhook**، الاستقصاء
الدوري هو الطريقة الوحيدة لمعرفة قرار مراجعة الموزّع.

```bash
curl http://72.62.41.242:8000/waslak/store-draft/uuid-here -H "X-API-Key: your-key"
```

Response:
```json
{
  "local_id": "uuid",
  "approval_status": "executed",
  "validation_errors": [],
  "waslak_draft_id": "cms...",
  "waslak_status": "PENDING",
  "merchant_id": null,
  "rejection_reason": null
}
```

---

### GET /waslak/merchants

قائمة تجار الموزّع (قراءة فقط، بلا موافقة). مفيدة قبل توليد مسودة جديدة للتأكد إن ما
فيه متجر مشابه أصلاً.

```bash
curl http://72.62.41.242:8000/waslak/merchants -H "X-API-Key: your-key"
```

---

### GET /waslak/merchants/{merchant_id}/insights

يجلب ملخص حالة طلبات التاجر من واصلك (pending/preparing/delivering/completed/cancelled)
ويولّد اقتراحات تحسين بالـ GPT — **قراءة فقط، بلا موافقة**، لكن يُخزَّن فوراً بنفس
الطلب (`waslak_insights`) — لا "توليد وننسى".

```bash
curl "http://72.62.41.242:8000/waslak/merchants/cms.../insights?merchant_name=Burger%20Spot" \
  -H "X-API-Key: your-key"
```

Response:
```json
{
  "insight_id": "uuid",
  "merchant_id": "cms...",
  "order_summary": {"pending": 5, "preparing": 2, "delivering": 1, "completed": 120, "cancelled": 3},
  "suggestions": "..."
}
```

يتطلب `WASLAK_BASE_URL` و `WASLAK_API_KEY` بالـ `.env` — بدونهم كل مسارات `/waslak/*`
اللي بتكلم واصلك ترجع `503` نظيف بدل ما تطيح.

---

### GET /approvals/{task_id}

```bash
curl http://72.62.41.242:8000/approvals/uuid-here \
  -H "X-API-Key: your-key"
```

---

### POST /approvals/decide

```bash
curl -X POST http://72.62.41.242:8000/approvals/decide \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "uuid-here",
    "approved": true,
    "note": "Looks good, send it"
  }'
```

---

## n8n Integration

في n8n، استبدل HTTP Request nodes بـ:

```
Telegram Input → POST /agent/plan → route by assigned_agent
    ↓
email_agent  → POST /email/draft → POST /agent/review → Send to Telegram
olivery_agent→ POST /olivery/report → POST /agent/review → Send to Telegram
file_agent   → POST /files/analyze-text → POST /agent/review → Send to Telegram
waslak_agent → POST /waslak/store-draft (waslak_store_draft) → Send to Telegram for approval
             → GET /waslak/merchants/{id}/insights (waslak_insights, no approval) → Send to Telegram
    ↓
If needs_user_confirmation → Send to Telegram → Wait for reply
    ↓
POST /approvals/decide → Execute if approved
```

---

## Approval Flow

```
طلب واصل → Supervisor (risk: medium)
    ↓
Agent يعمل → Reviewer يراجع
    ↓
needs_user_confirmation: true
    ↓
أواب يوصله على Telegram: "هل توافق على إرسال هذا الرد؟"
    ↓
أواب يرد: "نعم" → POST /approvals/decide {approved: true}
    ↓
Executor ينفذ (إرسال إيميل، تحديث بيانات، ...)
```

**القاعدة:** أي action خارجي (إرسال إيميل، تعديل بيانات) يحتاج موافقة صريحة.

---

## Database Tables

```
ai_tasks               — كل طلب يُنشئ task (channel_ref لمطابقة موافقات Telegram)
ai_task_steps          — خطوات تنفيذ كل task
ai_reviews             — قرار الـ reviewer لكل task
email_drafts           — مسودات الإيميلات (لا تُرسل بدون موافقة)
olivery_reports        — نتائج التقارير المخزنة
olivery_edit_requests  — تعديلات طلبات Olivery المُقترَحة (لا تُطبَّق بدون موافقة)
file_artifacts         — نتائج تحليل الملفات
audit_log              — سجل لا يُمسح لكل إجراء
waslak_store_drafts    — مسودات متاجر Waslak المُقترَحة (لا تُرسل لواصلك بدون موافقة)
waslak_insights        — تحليلات/اقتراحات تحسين محفوظة لكل تاجر Waslak
```

Run migrations:
```bash
./scripts/run_migrations.sh
```

يُطبّق أي ملف بمجلد `migrations/` لسه مش مسجّل بجدول `schema_migrations`، بترتيب
اسم الملف، ويسجّله بعد التطبيق. **آمن يتكرر تشغيله** — كل ملفات هذا المشروع
مكتوبة idempotent (`CREATE TABLE/INDEX/COLUMN IF NOT EXISTS`)، فإعادة تطبيق ملف
مطبَّق أصلاً لا يفعل شيء. شغّله بعد كل `git pull`/نشر بدل تخمين أي ملف جديد يدوياً.

> **لماذا أضيف هذا:** migration 006 كاملها ظلّت غير مُطبَّقة على قاعدة البيانات
> الفعلية لأسابيع رغم وجود ملفها بالمستودع طول الوقت — واكتُشفت بالصدفة فقط لما
> `/agent/plan` طاح بخطأ 500 (عمود `channel_ref` غير موجود). ما كان فيه أي طريقة
> نعرف فيها أي ملف اتنفذ فعلاً مقابل أي ملف موجود بس بالمجلد.

## متغيرات البيئة الإضافية (Waslak)

```
WASLAK_BASE_URL=https://<waslak-merchant-os-domain>
WASLAK_API_KEY=wsk_live_...   # مفتاح مربوط بموزّع واحد، من /distributor/settings/api-keys
```

## نشر تعديل كود (Deployment)

⚠️ **الحاوية بدون volume mount** — الكود يُنسخ داخل صورة Docker وقت البناء فقط
(`COPY app/ ./app/` بالـ Dockerfile). أي تعديل كود (وليس فقط `.env`) لازم:
```bash
docker compose up -d --build   # لا يكفي --restart وحده، الكود القديم بيضل شغال
```
تعديل `.env` فقط (متغيرات بيئة) يكفي معه `docker compose up -d` بدون `--build`.

## الأمان والشبكة (Postgres)

⚠️ **قاعدة البيانات (`awab-ai-postgres`, مُدارة من `/opt/awab-ai-postgres` على
السيرفر — مشروع منفصل تماماً عن هذا الريبو) كانت مكشوفة على الإنترنت العام حتى
2026-08-02** — تعليق بملف إعدادها كان يقول "مربوط على localhost فقط" بينما السطر
الفعلي تحته كان `ports: "5438:5432"` (أي `0.0.0.0`، بدون أي قيد). تم إصلاحها:

1. `awab-ai-gateway` انضمّت لشبكة `awab-ai-postgres_default` (`docker-compose.yml`
   بهذا الريبو، قسم `networks:`) وصارت تتصل عبر الاسم الداخلي
   `awab-ai-postgres:5432` بدل `host.docker.internal:5438` — لأن الأخير كان
   يعتمد على المنفذ المنشور على الاستضافة، والذي أُغلق بالخطوة التالية.
2. منفذ قاعدة البيانات المنشور (`5438`) صار مقيّداً بـ `127.0.0.1:5438:5432` —
   يبقى شغالاً بالكامل لأي SSH tunnel تطويري (`ssh -L 5438:127.0.0.1:5438 ...`)،
   لكنه لا يقبل أي اتصال من الإنترنت العام.

**لماذا التغيير مش مجرد "قيّد المنفذ":** `host.docker.internal` داخل حاوية
Docker يتحوّل فعلياً لعنوان جسر الشبكة (مثلاً `172.17.0.1`)، مش `127.0.0.1`
الحقيقي — فتقييد المنفذ بـ `127.0.0.1` وحده كان سيقطع اتصال `ai-gateway` نفسه
بقاعدة البيانات. الحل الصحيح (وهو الموصى به أصلاً بتوثيق `/opt/awab-ai-postgres`
نفسه تحت "النهج الأمثل على المدى البعيد") هو ضم الحاويتين لنفس شبكة Docker
والاتصال بالاسم الداخلي، لا الاعتماد على منفذ منشور على الاستضافة إطلاقاً.

**تحقق دوري:** `iptables -t nat -L -n | grep 5438` لازم يرجّع قاعدة DNAT
مقيّدة بوجهة `127.0.0.1` فقط — لو رجعت `0.0.0.0/0` فالتغيير انعكس (مثلاً بعد
إعادة تشغيل السيرفر بدون التحقق من `docker-compose.yml` بمجلد
`/opt/awab-ai-postgres`).

## حدود موارد الحاوية

نفس السيرفر يستضيف منصة واصلك الإنتاجية الحقيقية (تجار فعليين) بالإضافة لهذا
المشروع. `docker-compose.yml` يحدد لـ `awab-ai-gateway`:

```yaml
deploy:
  resources:
    limits:
      memory: 1g
      cpus: "1.0"
```

بدون هذا الحد، أي حلقة إعادة محاولة عالقة بـ GPT أو تحليل ملف كبير جداً ممكن
يستهلك موارد السيرفر (2 vCPU / 8GiB إجمالاً) ويأثر على حاويات واصلك المشتركة
بنفس الجهاز. تحقق بـ:
```bash
docker inspect awab-ai-gateway --format 'Memory={{.HostConfig.Memory}} NanoCpus={{.HostConfig.NanoCpus}}'
```
يجب أن يرجع `Memory=1073741824 NanoCpus=1000000000` — لو رجع `0 0` فالحد غير مطبَّق.
