"""Bounded Ollama streaming trial used by the persistent optimizer job."""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.optimizer.workloads import MAX_PROMPT_CHARACTERS, MAX_RESPONSE_TOKENS


class BenchmarkCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class TrialResult:
    ttft_ms: float | None
    prompt_tokens: int | None
    generated_tokens: int | None
    prompt_tokens_per_second: float | None
    generation_tokens_per_second: float | None
    load_duration_ms: float | None
    total_duration_ms: float | None
    wall_duration_ms: float
    output_characters: int
    finish_reason: str | None


def _rate(tokens: Any, duration_ns: Any) -> float | None:
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        return None
    if not isinstance(duration_ns, int) or isinstance(duration_ns, bool) or duration_ns <= 0:
        return None
    return round(tokens / (duration_ns / 1_000_000_000), 2)


def _milliseconds(duration_ns: Any) -> float | None:
    if not isinstance(duration_ns, int) or isinstance(duration_ns, bool) or duration_ns < 0:
        return None
    return round(duration_ns / 1_000_000, 1)


def _validated_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Invalid configured Ollama endpoint")
    return endpoint.rstrip("/")


def run_streamed_trial(
    endpoint: str,
    model_tag: str,
    prompt: str,
    options: dict[str, Any],
    cancel_event: threading.Event,
    *,
    transport: httpx.BaseTransport | None = None,
) -> TrialResult:
    if len(prompt) > MAX_PROMPT_CHARACTERS:
        raise ValueError("Synthetic benchmark prompt exceeds the safety bound")
    bounded_options = {
        "temperature": 0,
        "seed": 42,
        "num_predict": min(MAX_RESPONSE_TOKENS, max(1, int(options.get("num_predict", MAX_RESPONSE_TOKENS)))),
    }
    context = options.get("num_ctx")
    if isinstance(context, int) and not isinstance(context, bool) and 512 <= context <= 262_144:
        bounded_options["num_ctx"] = context

    payload = {
        "model": model_tag,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "think": False,
        "options": bounded_options,
    }
    started = time.perf_counter()
    first_token_at: float | None = None
    output_characters = 0
    final: dict[str, Any] | None = None
    timeout = httpx.Timeout(180.0, connect=5.0)

    with httpx.Client(
        base_url=_validated_endpoint(endpoint), timeout=timeout, transport=transport
    ) as client:
        with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if cancel_event.is_set():
                    raise BenchmarkCancelled("Benchmark cancellation requested")
                if not line:
                    continue
                if len(line) > 1_000_000:
                    raise ValueError("Ollama returned an oversized benchmark event")
                chunk = json.loads(line)
                if not isinstance(chunk, dict):
                    raise ValueError("Ollama returned an invalid benchmark event")
                content = chunk.get("message", {}).get("content", "")
                if isinstance(content, str) and content:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    output_characters += len(content)
                if chunk.get("done"):
                    final = chunk
                    break

    finished = time.perf_counter()
    if final is None:
        raise ValueError("Ollama stream ended without final metrics")
    return TrialResult(
        ttft_ms=round((first_token_at - started) * 1000, 1) if first_token_at else None,
        prompt_tokens=final.get("prompt_eval_count") if isinstance(final.get("prompt_eval_count"), int) else None,
        generated_tokens=final.get("eval_count") if isinstance(final.get("eval_count"), int) else None,
        prompt_tokens_per_second=_rate(final.get("prompt_eval_count"), final.get("prompt_eval_duration")),
        generation_tokens_per_second=_rate(final.get("eval_count"), final.get("eval_duration")),
        load_duration_ms=_milliseconds(final.get("load_duration")),
        total_duration_ms=_milliseconds(final.get("total_duration")),
        wall_duration_ms=round((finished - started) * 1000, 1),
        output_characters=output_characters,
        finish_reason=str(final.get("done_reason"))[:100] if final.get("done_reason") else None,
    )
