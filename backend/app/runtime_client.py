"""Runtime-independent local model access.

Ollama keeps its native internal protocol. Models served by llama.cpp,
LocalAI, vLLM, or another local OpenAI-compatible server use a prefixed model
reference so switching runtimes does not change the framework's client API.
"""

import ipaddress
import json
from collections.abc import Generator
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.ollama_client import (
    chat_stream as ollama_chat_stream,
    chat_structured as ollama_chat_structured,
    list_installed_models as list_ollama_models,
)
from app.optimizer.activity import ordinary_activity

LOCAL_OPENAI_PREFIX = "openai-local/"


class UnsafeRuntimeEndpoint(ValueError):
    pass


def validate_local_runtime_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeRuntimeEndpoint("The local runtime URL must use http:// or https://")
    if parsed.username or parsed.password:
        raise UnsafeRuntimeEndpoint("Credentials must not be embedded in the local runtime URL")
    if settings.allow_public_model_endpoints:
        return url

    host = parsed.hostname.lower().rstrip(".")
    allowed_names = {"localhost", "host.docker.internal", "gateway.docker.internal"}
    if host in allowed_names or "." not in host:
        return url
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise UnsafeRuntimeEndpoint(
            "Public model endpoints are disabled; use localhost, a private IP, or a Docker service name"
        ) from exc
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise UnsafeRuntimeEndpoint("Public model endpoints are disabled")
    return url


def _local_openai_url() -> str | None:
    if not settings.local_openai_base_url.strip():
        return None
    return validate_local_runtime_url(settings.local_openai_base_url)


def _headers() -> dict[str, str]:
    if not settings.local_openai_api_key:
        return {}
    return {"Authorization": f"Bearer {settings.local_openai_api_key}"}


def _provider_model_id(model_tag: str) -> str:
    if not model_tag.startswith(LOCAL_OPENAI_PREFIX):
        raise ValueError("Not a local OpenAI-compatible model reference")
    model_id = model_tag.removeprefix(LOCAL_OPENAI_PREFIX)
    if not model_id:
        raise ValueError("Local runtime model identifier is empty")
    return model_id


def list_local_openai_models() -> list[dict]:
    base_url = _local_openai_url()
    if base_url is None:
        return []
    response = httpx.get(f"{base_url}/models", headers=_headers(), timeout=10)
    response.raise_for_status()
    rows = response.json().get("data", [])
    return [
        {
            "name": str(row["id"]),
            "model": LOCAL_OPENAI_PREFIX + str(row["id"]),
            "size": 0,
            "modified_at": None,
            "details": {
                "family": "openai-compatible",
                "parameter_size": None,
                "quantization_level": None,
                "context_length": None,
                "provider": settings.local_openai_provider_name,
            },
        }
        for row in rows
        if isinstance(row, dict) and row.get("id")
    ]


def list_installed_models() -> list[dict]:
    models: list[dict] = []
    errors: list[Exception] = []
    try:
        models.extend(list_ollama_models())
    except (httpx.HTTPError, ValueError) as exc:
        errors.append(exc)
    try:
        models.extend(list_local_openai_models())
    except (httpx.HTTPError, ValueError) as exc:
        errors.append(exc)
    if models or not errors:
        return models
    raise errors[0]


def provider_capabilities() -> list[dict]:
    providers = [
        {
            "id": "ollama",
            "name": "Ollama",
            "configured": True,
            "protocol": "native",
            "capabilities": {
                "chat": True,
                "streaming": True,
                "structured_output": True,
                "embeddings": True,
                "tool_calling": False,
                "vision": False,
            },
        }
    ]
    configured = bool(settings.local_openai_base_url.strip())
    endpoint_safe = False
    error = None
    if configured:
        try:
            validate_local_runtime_url(settings.local_openai_base_url)
            endpoint_safe = True
        except UnsafeRuntimeEndpoint as exc:
            error = str(exc)
    providers.append(
        {
            "id": "openai-local",
            "name": settings.local_openai_provider_name,
            "configured": configured and endpoint_safe,
            "protocol": "openai-compatible",
            "endpoint": settings.local_openai_base_url if endpoint_safe else None,
            "error": error,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "structured_output": True,
                "embeddings": False,
                "tool_calling": False,
                "vision": False,
            },
        }
    )
    return providers


def _openai_chat_stream(model_tag: str, messages: list[dict], options: dict) -> Generator[dict, None, None]:
    base_url = _local_openai_url()
    if base_url is None:
        raise RuntimeError("The local OpenAI-compatible runtime is not configured")
    payload = {
        "model": _provider_model_id(model_tag),
        "messages": messages,
        "stream": True,
        "temperature": options.get("temperature"),
        "top_p": options.get("top_p"),
        "max_tokens": options.get("num_predict"),
        "stream_options": {"include_usage": True},
    }
    with ordinary_activity("chat"):
        with httpx.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers=_headers(),
            json=payload,
            timeout=httpx.Timeout(connect=10, read=300, write=30, pool=30),
        ) as response:
            response.raise_for_status()
            usage: dict = {}
            finish_reason = None
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                if isinstance(event.get("usage"), dict):
                    usage = event["usage"]
                choices = event.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                content = (choice.get("delta") or {}).get("content")
                if isinstance(content, str) and content:
                    yield {"type": "token", "text": content}
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
            yield {
                "type": "metrics",
                "prompt_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "finish_reason": finish_reason,
            }


def chat_stream(model_tag: str, messages: list[dict], options: dict) -> Generator[dict, None, None]:
    if model_tag.startswith(LOCAL_OPENAI_PREFIX):
        yield from _openai_chat_stream(model_tag, messages, options)
        return
    yield from ollama_chat_stream(model_tag, messages, options)


def chat_structured(model_tag: str, messages: list[dict], schema: dict) -> dict:
    if not model_tag.startswith(LOCAL_OPENAI_PREFIX):
        return ollama_chat_structured(model_tag, messages, schema)
    base_url = _local_openai_url()
    if base_url is None:
        raise RuntimeError("The local OpenAI-compatible runtime is not configured")
    payload = {
        "model": _provider_model_id(model_tag),
        "messages": messages,
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "framework_response", "strict": True, "schema": schema},
        },
    }
    with ordinary_activity("chat"):
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers=_headers(),
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Local runtime returned a structured response with the wrong type")
    return parsed
