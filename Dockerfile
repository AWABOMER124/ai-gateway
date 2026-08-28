FROM python:3.11-slim

WORKDIR /app

# تثبيت المكتبات أولاً (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# كسر الكاش — غيّر القيمة لإجبار إعادة البناء
ARG CACHEBUST=2
# نسخ الكود
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
