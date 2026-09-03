import json
from collections.abc import Generator

import httpx

from app.config import settings
from app.optimizer.activity import ordinary_activity


class EmbeddingError(RuntimeError):
    """An actionable failure while creating document-search embeddings."""


def list_installed_models() -> list[dict]:
    resp = httpx.get(f"{settings.ollama_host}/api/tags", timeout=10)
    resp.raise_for_status()
    return resp.json().get("models", [])


def embed(texts: list[str]) -> list[list[float]]:
    """Batch-embed text with the configured small, CPU-friendly embedding model.

    Keeping this separate from the main chat model reduces VRAM competition.
    """
    if not texts:
        return []
    payload = {"model": settings.embedding_model, "input": texts}
    try:
        with ordinary_activity("embedding"):
            resp = httpx.post(
                f"{settings.ollama_host}/api/embed",
                json=payload,
                timeout=httpx.Timeout(connect=10, read=300, write=30, pool=30),
            )
            resp.raise_for_status()
        body = resp.json()
        vectors = body.get("embeddings") if isinstance(body, dict) else None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise EmbeddingError(
                f"Embedding model '{settings.embedding_model}' is not installed in Ollama. "
                "Install it, then choose Retry indexing."
            ) from None
        raise EmbeddingError(
            f"Ollama could not index this document (HTTP {exc.response.status_code}). "
            "Check Ollama, then choose Retry indexing."
        ) from None
    except httpx.TimeoutException:
        raise EmbeddingError(
            "Ollama took too long to index this document. Check its CPU/GPU activity, "
            "then choose Retry indexing."
        ) from None
    except httpx.RequestError:
        raise EmbeddingError(
            "The framework could not reach Ollama to index this document. "
            "Start Ollama, then choose Retry indexing."
        ) from None
    except (ValueError, TypeError):
        raise EmbeddingError("Ollama returned an invalid embedding response. Update Ollama, then retry indexing.") from None

    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise EmbeddingError("Ollama returned an incomplete embedding response. Choose Retry indexing.")
    if any(not isinstance(vector, list) or len(vector) != settings.embedding_dimensions for vector in vectors):
        raise EmbeddingError(
            f"Embedding model '{settings.embedding_model}' returned the wrong vector size; "
            f"this framework expects {settings.embedding_dimensions}."
        )
    return vectors


def chat_structured(model_tag: str, messages: list[dict], schema: dict) -> dict:
    """Run a bounded, non-streaming Ollama request with a JSON-schema response contract."""
    payload = {
        "model": model_tag,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0.1, "num_predict": 4096},
    }
    with ordinary_activity("chat"):
        resp = httpx.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=180)
        resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Ollama returned a structured response with the wrong top-level type")
    return parsed


def chat_stream(model_tag: str, messages: list[dict], options: dict) -> Generator[dict, None, None]:
    """Yield assistant text plus Ollama's authoritative final timing/token metrics."""
    # Reasoning-capable models can return early output only in message.thinking,
    # which this user-facing chat intentionally does not expose. Keep hidden
    # reasoning off unless it becomes an explicit, safely rendered profile
    # option; otherwise the UI can appear to receive no answer at all.
    payload = {
        "model": model_tag,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": options,
    }
    with ordinary_activity("chat"):
        with httpx.stream(
            "POST",
            f"{settings.ollama_host}/api/chat",
            json=payload,
            timeout=httpx.Timeout(connect=10, read=300, write=30, pool=30),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield {"type": "token", "text": content}
                if chunk.get("done"):
                    yield {
                        "type": "metrics",
                        "prompt_tokens": chunk.get("prompt_eval_count"),
                        "output_tokens": chunk.get("eval_count"),
                        "prompt_eval_duration_ns": chunk.get("prompt_eval_duration"),
                        "generation_duration_ns": chunk.get("eval_duration"),
                        "load_duration_ns": chunk.get("load_duration"),
                        "total_duration_ns": chunk.get("total_duration"),
                        "finish_reason": chunk.get("done_reason"),
                    }
                    break
