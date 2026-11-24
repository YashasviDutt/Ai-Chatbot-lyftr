# LLM Chatbot with Key Failover and Response Caching

A full-stack AI chatbot built using React, FastAPI and SQLite, with LiteLLM as the LLM gateway and Groq for inference. The application supports automatic API key failover, response caching, session management and per-message token tracking.

## 1. Live URLs

- **Frontend:** https://ai-chatbot-lyftr.vercel.app/
- **Backend:** https://ai-chatbot-lyftr.onrender.com/
- **API Documentation:** https://ai-chatbot-lyftr.onrender.com/docs
- **Health Check:** https://ai-chatbot-lyftr.onrender.com/health
- **GitHub Repository:** https://github.com/YashasviDutt/Ai-Chatbot-lyftr

## 2. Run locally

### With Docker

Requirements: Docker, Docker Compose and Make.

```bash
cp .env.example .env
```

Configure at least two valid Groq API keys in `.env` and set the model to `groq/openai/gpt-oss-20b`.

```bash
make up
make down
```

Alternatively, on Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000

To stop the application:

```bash
docker compose down
```

### Without Docker

Backend:

```bash
cd backend
pip install -r requirements.txt

export LLM_API_KEYS=key1,key2
export LLM_MODEL=groq/openai/gpt-oss-20b
export DATABASE_URL=sqlite:///./app.db
export ENABLE_FAILURE_SIMULATION=true
export ALLOWED_ORIGINS=http://localhost:3000

uvicorn app.main:app --port 8000
```

Frontend, in a separate terminal from the project root:

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

Run automated tests:

```bash
cd backend
python -m pytest -q
```

Alternatively, using Docker from the project root:

```bash
docker compose exec backend python -m pytest tests/ -v -p no:cacheprovider
```

The automated tests do not require real API keys or external inference requests.

## 3. Design decisions

### Key fallback

`LLM_API_KEYS` is parsed into `key_1` through `key_N`. For every request, `llm.complete()` calls `litellm.completion()` with `key_1`.

If an exception occurs, including rate limits, quota exhaustion, server errors, authentication errors or timeouts, the application automatically attempts the next available key and increments `fallback_attempts`.

If all keys fail, the API returns HTTP 503:

```json
{ "detail": "all providers unavailable" }
```

Failed requests are not written to session history. API keys are never intentionally logged or returned in API responses; only their identifiers are exposed.

The fallback order is deterministic, making it easy to demonstrate and test. A production implementation could introduce per-key cooldowns and adaptive routing.

### Caching

The application uses LiteLLM's built-in response cache in local in-memory mode.

The cache key is based on the model and complete message list, including the system prompt and conversation history. API keys are excluded from the cache key.

Cache hits are detected through `_hidden_params["cache_hit"]` and return:

- `resolution_source: LLM_CACHE`
- `key_id: null`
- `fallback_attempts: 0`
- Original input and output token counts

Sending the same initial prompt in a new session retrieves the cached response. Different prompts or conversation histories generate separate cache entries.

Requests containing `X-Simulate-Failure` bypass cache reads to ensure the failover mechanism is exercised.

The in-memory cache is cleared when the backend restarts. Disk caching is supported when available in the installed LiteLLM version.

### SQLite session storage

The application uses a `messages` table and a `sessions` table to maintain conversation history and per-session system prompts.

An index on `(session_id, id)` supports ordered history retrieval.

The database schema is initialized automatically during application startup. WAL mode is enabled, and the local Docker configuration stores the database at `/data/app.db` using the `appdata` persistent volume.

User and assistant messages are written in a single transaction only after successful inference. Failed requests do not pollute conversation history.

### Failure simulation

The `X-Simulate-Failure` request header is supported when `ENABLE_FAILURE_SIMULATION=true`.

Selected keys raise simulated provider errors before making external inference calls.

Supported examples:

- `key_1=429`
- `key_1=500`
- `*=429`

This allows deterministic testing of API key fallback and complete provider failure.

## 4. Verification

The following commands can be executed using Bash or Git Bash.

```bash
B=https://ai-chatbot-lyftr.onrender.com

# Health check
curl "$B/health"

# Live inference
curl -s "$B/chat" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"a1","message":"What is the capital of France?"}'

# Cache hit in a new session
curl -s "$B/chat" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"a2","message":"What is the capital of France?"}'

# API key failover
curl -s "$B/chat" \
  -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"a3","message":"Tell me a joke"}'

# Complete provider failure
curl -si "$B/chat" \
  -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"a4","message":"Hi"}'

# Session history
curl -s "$B/sessions/a1/messages"

# Failed session verification
curl -si "$B/sessions/a4/messages"
```

Use fresh session IDs when repeating these tests. For local testing, replace the backend URL with `http://localhost:8000`.

The frontend displays the resolution source, model name, latency, input tokens, output tokens and API key identifier when applicable.

The Session Settings section provides an optional system prompt and failure simulation controls.

### Actual verification results

| Test                            | Result     |
| ------------------------------- | ---------- |
| Health endpoint                 | Passed     |
| Configured API keys             | 2          |
| Live inference                  | Passed     |
| Response caching                | Passed     |
| Identical cached response       | Passed     |
| Input and output token tracking | Passed     |
| API key failover                | Passed     |
| Session history retrieval       | Passed     |
| All-provider failure            | HTTP 503   |
| Failed session retrieval        | HTTP 404   |
| Automated backend tests         | 9/9 passed |

### Cache performance

| Metric            | Live inference | Cached response |
| ----------------- | -------------: | --------------: |
| Resolution source | LIVE_INFERENCE |       LLM_CACHE |
| Latency           |        2482 ms |         1964 ms |
| Input tokens      |             89 |              89 |
| Output tokens     |            105 |             105 |
| API key           |          key_1 |   Not displayed |

The recorded cache test demonstrated a latency reduction of approximately 20.9%, with identical response content and token usage.

### Failover verification

A simulated HTTP 429 error was applied to `key_1`.

- Resolution source: LIVE_INFERENCE
- Successful key: key_2
- Fallback attempts: 1
- Latency: 546 ms
- Input tokens: 88
- Output tokens: 168

Complete provider failure returned HTTP 503, and retrieving the failed session returned HTTP 404.

## 5. Setup Used

- **Developer:** Yashasvi Dutt Sharma
- **Editor:** Visual Studio Code
- **AI assistance:** OpenAI ChatGPT
- **Operating system:** Windows
- **Terminal:** PowerShell
- **Frontend:** React, Vite, CSS
- **Backend:** Python, FastAPI, Pydantic v2
- **LLM gateway:** LiteLLM
- **LLM provider:** Groq
- **Model:** groq/openai/gpt-oss-20b
- **Database:** SQLite
- **Testing:** Pytest
- **Containerization:** Docker, Docker Compose, Nginx
- **Version control:** Git and GitHub
- **Frontend hosting:** Vercel
- **Backend hosting:** Render

ChatGPT was used for implementation assistance, debugging, testing guidance, deployment configuration and documentation.

## 6. Bonus features

- Optional per-session system prompt.
- In-UI failure simulation controls.
- Live inference and cache hit badges.
- Per-message token usage and latency tracking.
- Automatic API key fallback.
- Interactive FastAPI Swagger documentation.
- Automated backend test suite using LiteLLM's mock response functionality.
- Multi-stage Docker builds.
- Non-root backend Docker container.
- Environment-based configuration.

## 7. Deployment notes

### Backend — Render

The backend is deployed as a Docker web service using the `backend` directory.

Required environment variables:

```env
LLM_API_KEYS=your_key_1,your_key_2
LLM_MODEL=groq/openai/gpt-oss-20b
DATABASE_URL=sqlite:////data/app.db
ALLOWED_ORIGINS=https://ai-chatbot-lyftr.vercel.app
ENABLE_FAILURE_SIMULATION=true
CACHE_TYPE=local
DEFAULT_SYSTEM_PROMPT=You are a helpful, concise assistant.
LLM_TIMEOUT_SECONDS=30
```

The container automatically honors the hosting platform's `PORT` environment variable.

### Frontend — Vercel

- Root directory: `frontend`
- Framework: Vite
- Build command: `npm run build`
- Output directory: `dist`

Environment variable:

```env
VITE_API_URL=https://ai-chatbot-lyftr.onrender.com
```

### Deployment limitations

The Render free-tier backend may experience cold starts after periods of inactivity.

Local Docker deployment uses a persistent named volume for SQLite. However, Render's free-tier filesystem is ephemeral, so database persistence across cloud restarts and redeployments is not guaranteed.

For durable cloud persistence, a persistent disk mounted at `/data` or an alternative hosting platform with persistent storage is required.

The local response cache is also cleared on backend restart.

Failure simulation is enabled for assignment evaluation and should be disabled or access-controlled in a production environment.

API keys are configured through environment variables and are excluded from the GitHub repository through `.gitignore`.

---

Developed by **Yashasvi Dutt Sharma** for the Lyftr AI Full-Stack Assignment.
