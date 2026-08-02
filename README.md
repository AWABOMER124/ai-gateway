# Awab AI Operator — API Gateway

FastAPI gateway يستقبل أسئلة، يبحث في قاعدة معرفة أواب بـ vector search، ويرجع إجابات عملية.

---

## ما هذا المشروع؟

```
n8n / Chatwoot / curl
        ↓
   POST /ask
        ↓
  vector search في ai_chunks (pgvector)
        ↓
  OpenAI Chat (gpt-4.1-mini)
        ↓
   إجابة بأسلوب أواب
```

**المتطلبات:**
- PostgreSQL + pgvector على `127.0.0.1:5438`
- جداول `ai_documents`, `ai_chunks`, `ai_queries` موجودة ومملوءة
- `OPENAI_API_KEY` صالح

---

## إعداد .env

```bash
cp .env.example .env
nano .env
```

```env
DATABASE_URL=postgresql://awab_ai:YOUR_PASSWORD@127.0.0.1:5438/awab_ai
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4.1-mini
DEFAULT_TOP_K=6
```

---

## التشغيل

### تثبيت المكتبات

```bash
pip install -r requirements.txt
```

### تشغيل بـ uvicorn

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8090
```

### تشغيل مع reload (للتطوير)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

### تشغيل بـ Docker Compose

```bash
docker compose up -d
docker compose logs -f
```

---

## أمثلة curl

### GET /health

```bash
curl http://127.0.0.1:8090/health
```

```json
{"status": "ok"}
```

---

### POST /search

```bash
curl -s -X POST http://127.0.0.1:8090/search \
  -H "Content-Type: application/json" \
  -d '{
    "question": "كيف أحلل متجر زياراته كثيرة ومبيعاته صفر؟",
    "top_k": 4
  }'
```

---

### POST /ask

```bash
curl -s -X POST http://127.0.0.1:8090/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "كيف أحلل متجر زياراته كثيرة ومبيعاته صفر؟",
    "top_k": 6,
    "show_sources": true
  }'
```

### مع تصفية حسب category

```bash
curl -s -X POST http://127.0.0.1:8090/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "جهز بريف حملة Easy Delivery للتجار",
    "category": "project",
    "project": "easy_delivery",
    "show_sources": true
  }'
```

### سؤال تقني

```bash
curl -s -X POST http://127.0.0.1:8090/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "كيف أشخص خطأ JSON parameter في n8n؟",
    "task_type": "debug",
    "show_sources": true
  }'
```

---

## الاستخدام مع n8n

**HTTP Request Node:**
- Method: `POST`
- URL: `http://127.0.0.1:8090/ask`
- Body Type: JSON

```json
{
  "question": "{{ $json.question }}",
  "top_k": 6,
  "show_sources": true
}
```

الرد: `{{ $json.answer }}`

---

## Endpoints

| Method | Path | الوصف |
|--------|------|-------|
| `GET` | `/health` | فحص الحالة |
| `POST` | `/ask` | سؤال → إجابة كاملة |
| `POST` | `/search` | بحث فقط بدون LLM |
| `GET` | `/docs` | Swagger UI |

---

## هيكل المشروع

```
app/
├── main.py              ← FastAPI app
├── config.py            ← إعدادات من .env
├── database.py          ← psycopg2 connection
├── rag/
│   ├── embeddings.py    ← get_embedding()
│   ├── search.py        ← search_chunks()
│   ├── prompt_builder.py ← system + user prompt
│   └── answer.py        ← generate_answer()
├── routers/
│   ├── health.py        ← GET /health
│   ├── ask.py           ← POST /ask
│   └── search.py        ← POST /search
└── schemas/
    ├── ask.py           ← AskRequest / AskResponse
    └── search.py        ← SearchRequest / SearchResponse
```
