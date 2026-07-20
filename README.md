# Suryaa Consumer Products — AI Assistant

## Deploy

### Local (Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Production (Docker)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t suryaa-ai .
docker run -p 8000:8000 suryaa-ai
```

### Cloud (Render / Railway / Fly.io)

```yaml
# render.yaml
services:
  - type: web
    name: suryaa-ai
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app:app --host 0.0.0.0 --port $PORT
```

## Test

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Why did SparkClean 1kg primary sales spike in Mumbai in the week of 16 Sep 2025?"}'

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What were GlucoJoy monthly primary sales vs target in the North region in November 2025?"}'
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/ask` | Ask a question → `{"answer", "intent", "citations", "confidence", "status"}` |
| GET | `/health` | Health check |
| GET | `/schema` | Data schema description |

## Response Contract

```json
{
  "answer": "string",
  "intent": "WHAT | WHY | WHAT_TO_DO | OUT_OF_DOMAIN",
  "citations": ["string"],
  "confidence": 0.95,
  "status": "OK | PENDING_APPROVAL | ABSTAINED"
}
```
