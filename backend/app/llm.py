"""LiteLLM gateway: key-pool failover + built-in response cache."""
import logging
import os

import litellm
from litellm import Cache

from .config import settings

log = logging.getLogger("llm")
litellm.suppress_debug_info = True


class AllProvidersUnavailable(Exception):
    pass


class SimulatedProviderError(Exception):
    def __init__(self, status: int):
        super().__init__(f"simulated provider status {status}")
        self.status = status


def init_cache() -> None:
    """In-memory cache by default. CACHE_TYPE=disk is used only if this LiteLLM version supports it."""
    if settings.cache_type == "disk":
        try:
            os.makedirs(settings.cache_dir, exist_ok=True)
            litellm.cache = Cache(type="disk", disk_cache_dir=settings.cache_dir)
            return
        except Exception as exc:
            log.warning("disk cache unsupported (%s); falling back to in-memory cache", type(exc).__name__)
    litellm.cache = Cache(type="local")


def parse_failure_header(value: str | None) -> dict[str, int]:
    """'key_1=429,key_2=500' or '*=429' -> {'key_1': 429, ...}"""
    out: dict[str, int] = {}
    if not value:
        return out
    for part in value.split(","):
        if "=" not in part:
            continue
        k, v = (s.strip() for s in part.split("=", 1))
        if k and v.isdigit() and int(v) in (429, 500, 502, 503):
            out[k] = int(v)
    return out


def complete(messages: list[dict], simulate: dict[str, int]) -> dict:
    """Try each key in order. Any failure moves on to the next key."""
    failures = 0
    for idx, api_key in enumerate(settings.api_keys, start=1):
        key_id = f"key_{idx}"
        status = simulate.get(key_id, simulate.get("*"))
        try:
            if status:
                raise SimulatedProviderError(status)
            kwargs = dict(
                model=settings.model,
                messages=messages,
                api_key=api_key,
                timeout=settings.request_timeout,
                num_retries=0,
                caching=True,
                drop_params=True,
            )
            if simulate:
                # failure-simulation requests must exercise the key pool, so skip cache reads
                kwargs["cache"] = {"no-cache": True}
            if settings.mock_llm:
                kwargs["mock_response"] = "Mock reply to: " + messages[-1]["content"]
            resp = litellm.completion(**kwargs)
            reply = (resp.choices[0].message.content or "").strip()
            if not reply:
                raise ValueError("empty completion")
        except Exception as exc:  # 429, quota, 5xx, auth, timeout... -> next key
            failures += 1
            log.warning(
                "%s failed (%s); missing module: %s",
                key_id,
                type(exc).__name__,
                getattr(exc, "name", None)
            )
            continue

        usage = getattr(resp, "usage", None)
        hidden = getattr(resp, "_hidden_params", None) or {}
        cache_hit = bool(hidden.get("cache_hit"))
        return {
            "reply": reply,
            "cache_hit": cache_hit,
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "key_id": None if cache_hit else key_id,
            "fallback_attempts": 0 if cache_hit else failures,
        }
    raise AllProvidersUnavailable()
