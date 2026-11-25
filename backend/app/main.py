import os
import time
from datetime import datetime, timezone
from typing import Optional

import litellm
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from litellm import Cache

from .database import add_exchange, connection, get_messages, init_db

DEFAULT_SYSTEM_PROMPT = os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise assistant.")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
KEYS = [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]
FAILURE_SIM = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
CACHE_TYPE = os.getenv("LITELLM_CACHE_TYPE", "disk")
CACHE_DIR = os.getenv("LITELLM_CACHE_DIR", "/data/litellm_cache")

if CACHE_TYPE == "disk":
    os.makedirs(CACHE_DIR, exist_ok=True)
    litellm.cache = Cache(type="disk", disk_cache_dir=CACHE_DIR)
else:
    litellm.cache = Cache(type="local")

app = FastAPI(title="Lyftr AI Chatbot")
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: Optional[str] = None

    @field_validator("session_id", "message")
    @classmethod
    def non_blank(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


def parse_simulation(value: Optional[str]) -> dict[str, int]:
    if not value or not FAILURE_SIM:
        return {}
    result = {}
    for part in value.split(","):
        key, sep, status = part.strip().partition("=")
        if not sep or status not in {"429", "500", "502", "503"}:
            continue
        result[key] = int(status)
    return result


def should_fail(sim: dict[str, int], key_id: str):
    return sim.get(key_id) or sim.get("*")


def is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    return status in {429, 500, 502, 503} or "quota" in text or "rate limit" in text


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    if len(KEYS) < 2:
        raise HTTPException(status_code=503, detail="key pool not loaded")
    return {"status": "ok", "keys_configured": len(KEYS), "cache_enabled": litellm.cache is not None}


@app.post("/chat")
async def chat(body: ChatRequest, x_simulate_failure: Optional[str] = Header(default=None, alias="X-Simulate-Failure")):
    stored = get_messages(body.session_id)
    history = [{"role": m["role"], "content": m["content"]} for m in stored]
    messages = [{"role": "system", "content": body.system_prompt or DEFAULT_SYSTEM_PROMPT}, *history, {"role": "user", "content": body.message}]
    sim = parse_simulation(x_simulate_failure)
    started = time.perf_counter()
    failed = 0

    for index, api_key in enumerate(KEYS, start=1):
        key_id = f"key_{index}"
        if should_fail(sim, key_id):
            failed += 1
            continue
        try:
            response = await litellm.acompletion(
                model=LLM_MODEL,
                messages=messages,
                api_key=api_key,
                caching=True,
                max_retries=0,
            )
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            hidden = getattr(response, "_hidden_params", {}) or {}
            cache_hit = bool(hidden.get("cache_hit") or hidden.get("cached_response"))
            usage = getattr(response, "usage", None)
            reply = response.choices[0].message.content or ""
            if not reply.strip():
                raise RuntimeError("provider returned empty reply")
            metadata = {
                "resolution_source": "LLM_CACHE" if cache_hit else "LIVE_INFERENCE",
                "model": LLM_MODEL,
                "latency_ms": latency_ms,
                "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "key_id": None if cache_hit else key_id,
                "fallback_attempts": 0 if cache_hit else failed,
            }
            add_exchange(body.session_id, body.message, reply, metadata, datetime.now(timezone.utc).isoformat())
            return {"session_id": body.session_id, "reply": reply, "metadata": metadata}
        except Exception as exc:
            if is_retryable(exc):
                failed += 1
                continue
            # Provider/auth failures also permit trying the remaining configured keys.
            failed += 1
            continue

    raise HTTPException(status_code=503, detail="all providers unavailable")


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    messages = get_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": messages}
