import json
import logging
import time
import uuid
from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.db import SessionLocal, get_db
from app.deps import get_active_model_profile, get_current_user
from app.domain_model_settings import effective_model_settings, fit_messages_to_context, ollama_options
from app.learning_cards import LearningCardSourceTooLong, generate_learning_cards
from app.models import Conversation, Domain, Message, MessageRole
from app.ollama_client import chat_stream
from app.optimizer.activity import OllamaBusyError, snapshot as ollama_activity_snapshot
from app.prompt_assembly import assemble, log_retrieval, log_scope_access
from app.routers.domains import get_owned_domain_or_404
from app.schemas import ChatMessageIn, ConversationDetailOut, ConversationOut, LearningCardSetOut

router = APIRouter(tags=["chat"], dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)

EMPTY_RESPONSE_FALLBACK = (
    "I couldn't produce a reliable answer from the available context. Could you rephrase your "
    "request and include the specific outcome or information you need?"
)
ERROR_RESPONSE_FALLBACK = (
    "The local model could not complete this response. Please check that Ollama and the selected "
    "model are available, then retry your prompt."
)
PARTIAL_RESPONSE_NOTICE = (
    "\n\n[Generation stopped unexpectedly. The response above may be incomplete; please retry.]"
)
BENCHMARK_BUSY_FALLBACK = (
    "The local model is currently running a Model Performance Optimizer benchmark. "
    "Wait for it to finish or cancel it in the performance panel, then retry this prompt."
)


def _options(profile) -> dict:
    """Retain the framework-profile option helper for optimizer compatibility."""
    return {
        "temperature": profile.temperature,
        "top_p": profile.top_p,
        "top_k": profile.top_k,
        "repeat_penalty": profile.repeat_penalty,
        "num_ctx": profile.context_length,
    }


def _stream_and_persist(
    model_tag: str,
    messages: list[dict],
    options: dict,
    layers: list[dict],
    citations: list[dict],
    conv_id: uuid.UUID,
) -> Generator[str, None, None]:
    yield json.dumps({"type": "prompt", "layers": layers}) + "\n"
    full_text = ""
    stream_started = time.perf_counter()
    first_token_at: float | None = None
    raw_metrics: dict = {}
    generation_error = False
    try:
        for event in chat_stream(model_tag, messages, options):
            if event.get("type") == "token":
                chunk = event.get("text", "")
                if not chunk:
                    continue
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                full_text += chunk
                yield json.dumps({"type": "token", "text": chunk}) + "\n"
            elif event.get("type") == "metrics":
                raw_metrics = event
    except OllamaBusyError:
        generation_error = True
        raw_metrics["busy_reason"] = "optimizer_benchmark"
    except Exception:  # noqa: BLE001 - a visible, persisted outcome is required for every prompt
        generation_error = True
        logger.exception("Local model generation failed for conversation %s", conv_id)

    if generation_error:
        fallback = (
            PARTIAL_RESPONSE_NOTICE
            if full_text.strip()
            else BENCHMARK_BUSY_FALLBACK
            if raw_metrics.get("busy_reason") == "optimizer_benchmark"
            else ERROR_RESPONSE_FALLBACK
        )
        full_text += fallback
        if first_token_at is None:
            first_token_at = time.perf_counter()
        yield json.dumps({"type": "token", "text": fallback}) + "\n"
        status = "error_fallback"
    elif not full_text.strip():
        full_text = EMPTY_RESPONSE_FALLBACK
        first_token_at = time.perf_counter()
        yield json.dumps({"type": "token", "text": full_text}) + "\n"
        status = "empty_fallback"
    elif raw_metrics.get("finish_reason") == "length":
        notice = "\n\n[This answer reached the domain's answer-length limit. Ask to continue or increase it in Domain model settings.]"
        full_text += notice
        yield json.dumps({"type": "token", "text": notice}) + "\n"
        status = "truncated"
    else:
        status = "completed"

    generation_duration_ns = raw_metrics.get("generation_duration_ns")
    output_tokens = raw_metrics.get("output_tokens")
    tokens_per_second = None
    if output_tokens is not None and generation_duration_ns:
        tokens_per_second = output_tokens / (generation_duration_ns / 1_000_000_000)

    metrics = {
        "prompt_tokens": raw_metrics.get("prompt_tokens"),
        "output_tokens": output_tokens,
        "tokens_per_second": round(tokens_per_second, 2) if tokens_per_second is not None else None,
        "time_to_first_token_ms": (
            round((first_token_at - stream_started) * 1000, 1) if first_token_at is not None else None
        ),
        "prompt_eval_duration_ms": _ns_to_ms(raw_metrics.get("prompt_eval_duration_ns")),
        "generation_duration_ms": _ns_to_ms(generation_duration_ns),
        "load_duration_ms": _ns_to_ms(raw_metrics.get("load_duration_ns")),
        "total_duration_ms": _ns_to_ms(raw_metrics.get("total_duration_ns")),
        "finish_reason": raw_metrics.get("finish_reason"),
        "status": status,
    }

    with SessionLocal() as gdb:
        msg = Message(
            conversation_id=conv_id,
            role=MessageRole.assistant,
            content=full_text,
            citations=citations,
            generation_metrics=metrics,
        )
        gdb.add(msg)
        gdb.commit()
        gdb.refresh(msg)
        message_id = msg.id

    yield json.dumps(
        {
            "type": "done",
            "conversation_id": str(conv_id),
            "message_id": str(message_id),
            "citations": citations,
            "metrics": metrics,
        }
    ) + "\n"


def _ns_to_ms(value: int | None) -> float | None:
    return round(value / 1_000_000, 1) if value is not None else None


@router.get("/domains/{domain_id}/conversations", response_model=list[ConversationOut])
def list_conversations(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    return (
        db.query(Conversation)
        .filter_by(domain_id=scope.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    conv = db.query(Conversation).filter_by(id=conversation_id, user_id=user.id).one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def _latest_message(db: Session, conversation_id: uuid.UUID) -> Message | None:
    return (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )


@router.post(
    "/conversations/{conversation_id}/learning-cards",
    response_model=LearningCardSetOut,
)
def create_learning_cards(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    conv = db.query(Conversation).filter_by(id=conversation_id, user_id=user.id).one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    source_message = _latest_message(db, conv.id)
    if source_message is None or source_message.role != MessageRole.assistant:
        raise HTTPException(
            status_code=409,
            detail="The latest assistant response is not ready yet",
        )
    generation_status = (source_message.generation_metrics or {}).get("status")
    if generation_status and generation_status != "completed":
        raise HTTPException(
            status_code=409,
            detail="Learning cards require a completed assistant response",
        )
    scope_settings = effective_model_settings(db, db.get(Domain, conv.domain_id))
    if scope_settings is None:
        raise HTTPException(status_code=400, detail="No active model selected")
    if ollama_activity_snapshot().benchmark_run_id is not None:
        raise HTTPException(status_code=409, detail=BENCHMARK_BUSY_FALLBACK)

    try:
        draft = generate_learning_cards(scope_settings.model_tag, source_message.content)
    except LearningCardSourceTooLong as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except OllamaBusyError as exc:
        raise HTTPException(status_code=409, detail=BENCHMARK_BUSY_FALLBACK) from exc
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Learning-card model returned invalid output: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="The local model could not create valid learning cards. Try again.",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - normalize local model/network failures
        logger.exception("Learning-card generation failed for conversation %s", conv.id)
        raise HTTPException(
            status_code=502,
            detail="The local model could not create learning cards. Check Ollama and try again.",
        ) from exc

    # A second tab may have added or regenerated a response while the model was
    # compacting. Never attach a deck to a response that is no longer latest.
    current_latest = _latest_message(db, conv.id)
    if current_latest is None or current_latest.id != source_message.id:
        raise HTTPException(
            status_code=409,
            detail="A newer message arrived. Run Learning cards again on the latest response.",
        )

    card_set = LearningCardSetOut(
        **draft.model_dump(),
        source_message_id=source_message.id,
        model_tag=scope_settings.model_tag,
        created_at=datetime.now(timezone.utc),
    )
    source_message.learning_cards = card_set.model_dump(mode="json")
    log_scope_access(db, user.id, db.get(Domain, conv.domain_id), context="learning_cards")
    db.commit()
    return card_set


@router.delete("/domains/{domain_id}/conversations/{conversation_id}")
def delete_conversation(
    domain_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    conv = (
        db.query(Conversation)
        .filter_by(id=conversation_id, domain_id=scope.id, user_id=user.id)
        .one_or_none()
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found in this scope")

    # A SQL-level delete lets PostgreSQL enforce the declared cascades for messages and
    # retrieval logs. Manually-saved memories intentionally survive with conversation_id=NULL.
    result = db.execute(
        delete(Conversation).where(
            Conversation.id == conv.id,
            Conversation.domain_id == scope.id,
            Conversation.user_id == user.id,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conversation changed during deletion")
    db.commit()
    return {"ok": True}


@router.post("/domains/{domain_id}/messages")
def send_message(domain_id: uuid.UUID, body: ChatMessageIn, db: Session = Depends(get_db)):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    model_settings = effective_model_settings(db, scope)
    if model_settings is None:
        raise HTTPException(status_code=400, detail="No active model selected")

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text is required")
    if ollama_activity_snapshot().benchmark_run_id is not None:
        raise HTTPException(status_code=409, detail=BENCHMARK_BUSY_FALLBACK)

    if body.conversation_id is not None:
        conv = db.get(Conversation, body.conversation_id)
        if conv is None or conv.domain_id != scope.id:
            raise HTTPException(status_code=404, detail="Conversation not found in this scope")
    else:
        title = text[:34] + ("…" if len(text) > 34 else "")
        conv = Conversation(user_id=user.id, domain_id=scope.id, title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)

    history = list(conv.messages)
    result = assemble(db, scope, history, text)
    fitted_messages = fit_messages_to_context(
        result.messages, model_settings.context_length, model_settings.max_output_tokens
    )

    db.add(Message(conversation_id=conv.id, role=MessageRole.user, content=text))
    db.commit()
    log_scope_access(db, user.id, scope, context="chat")
    log_retrieval(db, user.id, scope, text, result, conversation_id=conv.id)

    return StreamingResponse(
        _stream_and_persist(
            model_settings.model_tag,
            fitted_messages,
            ollama_options(model_settings),
            result.layers,
            result.citations,
            conv.id,
        ),
        media_type="application/x-ndjson",
    )


@router.post("/conversations/{conversation_id}/regenerate")
def regenerate(conversation_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    conv = db.query(Conversation).filter_by(id=conversation_id, user_id=user.id).one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    scope = db.get(Domain, conv.domain_id)
    model_settings = effective_model_settings(db, scope)
    if model_settings is None:
        raise HTTPException(status_code=400, detail="No active model selected")
    if ollama_activity_snapshot().benchmark_run_id is not None:
        raise HTTPException(status_code=409, detail=BENCHMARK_BUSY_FALLBACK)

    messages = list(conv.messages)
    if messages and messages[-1].role == MessageRole.assistant:
        db.delete(messages[-1])
        db.commit()
        messages = messages[:-1]
    if not messages or messages[-1].role != MessageRole.user:
        raise HTTPException(status_code=400, detail="No user message to regenerate a reply for")

    last_user_text = messages[-1].content
    history = messages[:-1]
    result = assemble(db, scope, history, last_user_text)
    fitted_messages = fit_messages_to_context(
        result.messages, model_settings.context_length, model_settings.max_output_tokens
    )
    log_scope_access(db, user.id, scope, context="chat_regenerate")
    log_retrieval(db, user.id, scope, last_user_text, result, conversation_id=conv.id)

    return StreamingResponse(
        _stream_and_persist(
            model_settings.model_tag,
            fitted_messages,
            ollama_options(model_settings),
            result.layers,
            result.citations,
            conv.id,
        ),
        media_type="application/x-ndjson",
    )
