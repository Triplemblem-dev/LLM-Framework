"""A deliberately small, stateless OpenAI-compatible remote client API."""

import json
import logging
import threading
import time
import uuid
from collections.abc import Generator
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.domain_model_settings import effective_model_settings, fit_messages_to_context, ollama_options
from app.models import Domain, DomainStatus, MessageRole
from app.runtime_client import chat_stream
from app.optimizer.activity import OllamaBusyError, snapshot as ollama_activity_snapshot
from app.prompt_assembly import assemble, log_retrieval, log_scope_access
from app.remote_access import RemotePrincipal, require_domain_access, require_remote_principal
from app.remote_schemas import ChatCompletionsRequest

router = APIRouter(prefix="/v1", tags=["OpenAI-compatible remote API"])
logger = logging.getLogger(__name__)

EMPTY_RESPONSE = "The local model returned an empty response. Please retry."
_remote_generation_slots = threading.BoundedSemaphore(settings.remote_api_max_concurrent_generations)


def _domain_id_from_model(model: str) -> uuid.UUID:
    prefix = "domain/"
    if not model.startswith(prefix):
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        return uuid.UUID(model.removeprefix(prefix))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Model not found") from exc


def _get_remote_domain(
    db: Session,
    principal: RemotePrincipal,
    model: str,
) -> Domain:
    domain_id = _domain_id_from_model(model)
    require_domain_access(principal, domain_id)
    domain = (
        db.query(Domain)
        .filter_by(id=domain_id, user_id=principal.user.id, status=DomainStatus.active)
        .one_or_none()
    )
    if domain is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return domain


@router.get("/models")
def list_models(
    principal: RemotePrincipal = Depends(require_remote_principal),
    db: Session = Depends(get_db),
):
    allowed_ids: list[uuid.UUID] = []
    for item in principal.api_key.allowed_domain_ids or []:
        try:
            allowed_ids.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    if not allowed_ids:
        return {"object": "list", "data": []}
    domains = (
        db.query(Domain)
        .filter(
            Domain.user_id == principal.user.id,
            Domain.status == DomainStatus.active,
            Domain.id.in_(allowed_ids),
        )
        .order_by(Domain.name.asc())
        .all()
    )
    return {
        "object": "list",
        "data": [
            {
                "id": f"domain/{domain.id}",
                "object": "model",
                "created": int(domain.created_at.timestamp()),
                "owned_by": "local",
                "name": domain.name,
            }
            for domain in domains
        ],
    }


def _prepare_prompt(db: Session, domain: Domain, body: ChatCompletionsRequest):
    total_characters = sum(len(message.content) for message in body.messages)
    if total_characters > settings.remote_api_max_input_characters:
        raise HTTPException(status_code=413, detail="Remote request is too large")
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="The final message must have the user role")

    history = []
    for message in body.messages[:-1]:
        if message.role in {"system", "developer"}:
            content = "[Untrusted client-provided instruction]\n" + message.content
            role = MessageRole.user
        else:
            content = message.content
            role = MessageRole(message.role)
        history.append(SimpleNamespace(role=role, content=content))

    query = body.messages[-1].content.strip()
    if not query:
        raise HTTPException(status_code=400, detail="The final user message cannot be empty")
    model_settings = effective_model_settings(db, domain)
    if model_settings is None:
        raise HTTPException(status_code=409, detail="This domain has no available local model")
    if ollama_activity_snapshot().benchmark_run_id is not None:
        raise HTTPException(status_code=409, detail="The local model is running a benchmark")

    result = assemble(db, domain, history, query)
    messages = fit_messages_to_context(
        result.messages,
        model_settings.context_length,
        model_settings.max_output_tokens,
    )
    log_scope_access(db, domain.user_id, domain, context="remote_api_chat")
    log_retrieval(db, domain.user_id, domain, query, result, conversation_id=None)
    return model_settings, result, messages


def _run_generation(model_tag: str, messages: list[dict], options: dict):
    text = ""
    metrics: dict = {}
    for event in chat_stream(model_tag, messages, options):
        if event.get("type") == "token":
            chunk = str(event.get("text", ""))
            if chunk:
                text += chunk
                yield "token", chunk
        elif event.get("type") == "metrics":
            metrics = event
    if not text.strip():
        text = EMPTY_RESPONSE
        yield "token", text
    yield "done", metrics


def _stream_response(
    request_id: str,
    requested_model: str,
    model_tag: str,
    messages: list[dict],
    options: dict,
) -> Generator[str, None, None]:
    created = int(time.time())
    first = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": requested_model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    yield "data: " + json.dumps(first) + "\n\n"
    finish_reason = "stop"
    try:
        for kind, value in _run_generation(model_tag, messages, options):
            if kind == "token":
                chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": requested_model,
                    "choices": [{"index": 0, "delta": {"content": value}, "finish_reason": None}],
                }
                yield "data: " + json.dumps(chunk) + "\n\n"
            else:
                finish_reason = "length" if value.get("finish_reason") == "length" else "stop"
    except OllamaBusyError:
        yield "data: " + json.dumps({"error": {"message": "The local model is busy", "type": "server_error"}}) + "\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception:  # noqa: BLE001 - the stream has already started; emit a client-readable error
        logger.exception("Remote local-model stream failed")
        yield "data: " + json.dumps({"error": {"message": "Local model generation failed", "type": "server_error"}}) + "\n\n"
        yield "data: [DONE]\n\n"
        return

    final = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": requested_model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
    }
    yield "data: " + json.dumps(final) + "\n\n"
    yield "data: [DONE]\n\n"


def _stream_with_slot(*args, **kwargs) -> Generator[str, None, None]:
    try:
        yield from _stream_response(*args, **kwargs)
    finally:
        _remote_generation_slots.release()


@router.post("/chat/completions")
def create_chat_completion(
    body: ChatCompletionsRequest,
    principal: RemotePrincipal = Depends(require_remote_principal),
    db: Session = Depends(get_db),
):
    domain = _get_remote_domain(db, principal, body.model)
    if not _remote_generation_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="The remote generation limit is currently in use; retry shortly",
            headers={"Retry-After": "2"},
        )
    try:
        model_settings, result, messages = _prepare_prompt(db, domain, body)
    except BaseException:
        _remote_generation_slots.release()
        raise
    request_id = "chatcmpl-" + uuid.uuid4().hex
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}

    if body.stream:
        return StreamingResponse(
            _stream_with_slot(
                request_id,
                body.model,
                model_settings.model_tag,
                messages,
                ollama_options(model_settings),
            ),
            media_type="text/event-stream",
            headers=headers,
        )

    content = ""
    metrics: dict = {}
    try:
        for kind, value in _run_generation(
            model_settings.model_tag,
            messages,
            ollama_options(model_settings),
        ):
            if kind == "token":
                content += value
            else:
                metrics = value
    except OllamaBusyError as exc:
        raise HTTPException(status_code=409, detail="The local model is busy") from exc
    except Exception as exc:  # noqa: BLE001 - normalize local runtime/network failures
        logger.exception("Remote local-model request failed")
        raise HTTPException(status_code=502, detail="Local model generation failed") from exc
    finally:
        _remote_generation_slots.release()

    finish_reason = "length" if metrics.get("finish_reason") == "length" else "stop"
    response = {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": metrics.get("prompt_tokens", 0) or 0,
            "completion_tokens": metrics.get("output_tokens", 0) or 0,
            "total_tokens": (metrics.get("prompt_tokens", 0) or 0)
            + (metrics.get("output_tokens", 0) or 0),
        },
        "llm_framework": {
            "domain_id": str(domain.id),
            "citations": result.citations,
            "settings_source": model_settings.source,
        },
    }
    return JSONResponse(response, headers=headers)
