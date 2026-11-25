# Lyftr AI Full-Stack Assignment

A React + FastAPI + SQLite chatbot using LiteLLM with per-request metadata, response caching and API-key failover.

## 1. Live URLs

- Frontend: `ADD_FRONTEND_URL`
- Backend: `ADD_BACKEND_URL`
- Health: `ADD_BACKEND_URL/health`

## 2. Run locally: with Docker and without

### Docker
```bash
cp .env.example .env
# Put two real provider keys in LLM_API_KEYS.
make up
```
Frontend: http://localhost:3000  
Backend: http://localhost:8000

Stop with `make down`.

### Without Docker
Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export LLM_API_KEYS="key1,key2"
export DATABASE_URL="sqlite:///./app.db"
export ENABLE_FAILURE_SIMULATION=true
uvicorn app.main:app --reload --port 8000
```
Frontend:
```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

## 3. Design decisions: key fallback, caching, SQLite session storage

**Key fallback.** `LLM_API_KEYS` is parsed in order as `key_1`, `key_2`, etc. Each `/chat` request attempts keys sequentially. Rate-limit/quota/5xx failures move to the next key. `X-Simulate-Failure` skips selected keys for only that request, making failover deterministic and easy to demonstrate.

**Caching.** LiteLLM's built-in cache is enabled on completion calls. Disk cache is the default so cached results survive backend restarts when `/data` is persisted. Because the LLM request contains model + system prompt + full stored history + new message, exact first-turn requests in new sessions share the same cache key while different conversations do not.

**SQLite.** Only successful exchanges are written. The client sends only the newest message; the backend reconstructs history from SQLite before inference. The database lives at `DATABASE_URL`, normally `/data/app.db` in Docker.

## 4. Verification: how to see failover, cache hits and per-message token usage

Health:
```bash
curl http://localhost:8000/health
```

Live inference:
```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"session_id":"s-one","message":"What is the capital of France?"}'
```

Cache hit: send the same first message with a new session id. Confirm `resolution_source` is `LLM_CACHE`, reply is identical, `key_id` is null and latency is lower.

Failover:
```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=429' -d '{"session_id":"s-failover","message":"Say hello in one sentence."}'
```
Confirm HTTP 200, `key_id: key_2`, and `fallback_attempts: 1`.

All providers unavailable:
```bash
curl -i -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: *=429' -d '{"session_id":"s-down","message":"hello"}'
```
Confirm 503 with `{"detail":"all providers unavailable"}` and no history for `s-down`.

History:
```bash
curl http://localhost:8000/sessions/s-one/messages
```

The frontend renders input/output token usage and latency beside every assistant reply.

## 5. Setup Used: your editor and AI tools

- Editor: VS Code
- AI assistance: ChatGPT for architecture review, implementation assistance and documentation
- Framework/documentation references: FastAPI, React/Vite and LiteLLM docs

## 6. Bonus features (if any): what you added beyond the requirements and why

- Responsive, polished UI with clear live/cache badges.
- Optional system-prompt input.
- Disk-backed LiteLLM cache for better restart resilience.
- Atomic user/assistant history writes to avoid partial successful exchanges.

## Deployment notes

Deploy the backend with a persistent disk mounted at `/data`, set all backend environment variables, and keep `ENABLE_FAILURE_SIMULATION=true` for evaluation. Deploy the frontend with `VITE_API_URL` set to the public backend URL. Then set backend `ALLOWED_ORIGINS` to the exact public frontend origin and redeploy.
