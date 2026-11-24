import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from . import db, llm
from .config import settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    llm.init_cache()
    yield


app = FastAPI(title="LLM Chatbot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    system_prompt: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]] = None


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception):
    logging.getLogger("app").exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/health")
def health():
    ok = db.ping() and len(settings.api_keys) > 0
    body = {
        "status": "ok" if ok else "unavailable",
        "keys_configured": len(settings.api_keys),
        "cache_enabled": llm.litellm.cache is not None,
    }
    return JSONResponse(status_code=200 if ok else 503, content=body)


@app.post("/chat")
def chat(req: ChatRequest, x_simulate_failure: Optional[str] = Header(default=None)):
    start = time.perf_counter()
    system_prompt = req.system_prompt or db.get_session_prompt(req.session_id) or settings.default_system_prompt
    messages = (
        [{"role": "system", "content": system_prompt}]
        + db.get_history(req.session_id)
        + [{"role": "user", "content": req.message}]
    )
    simulate = llm.parse_failure_header(x_simulate_failure) if settings.enable_failure_simulation else {}

    try:
        result = llm.complete(messages, simulate)
    except llm.AllProvidersUnavailable:
        return JSONResponse(status_code=503, content={"detail": "all providers unavailable"})

    metadata = {
        "resolution_source": "LLM_CACHE" if result["cache_hit"] else "LIVE_INFERENCE",
        "model": settings.model,
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "key_id": result["key_id"],
        "fallback_attempts": result["fallback_attempts"],
    }
    db.save_exchange(req.session_id, req.system_prompt or None, req.message, result["reply"], metadata)
    return {"session_id": req.session_id, "reply": result["reply"], "metadata": metadata}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    msgs = db.get_messages(session_id)
    if not msgs:
        return JSONResponse(status_code=404, content={"detail": "session not found"})
    return {"session_id": session_id, "messages": msgs}
