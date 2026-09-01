from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Domain, Model, ModelProfile


DEFAULT_MAX_OUTPUT_TOKENS = 2048


@dataclass(frozen=True)
class EffectiveModelSettings:
    model_tag: str
    context_length: int
    max_output_tokens: int
    temperature: float
    top_p: float
    top_k: int
    repeat_penalty: float
    source: str


def effective_model_settings(db: Session, domain: Domain) -> EffectiveModelSettings | None:
    saved = domain.model_settings or {}
    active = db.query(ModelProfile).filter_by(is_active=True).one_or_none()
    saved_tag = saved.get("model_tag")
    model = db.query(Model).filter_by(ollama_tag=saved_tag).one_or_none() if saved_tag else None
    profile = db.query(ModelProfile).filter_by(model_id=model.id).one_or_none() if model else active
    if profile is None:
        return None

    context = int(saved.get("context_length", profile.context_length))
    context = max(512, min(262_144, context))
    max_output = int(saved.get("max_output_tokens", min(DEFAULT_MAX_OUTPUT_TOKENS, context // 2)))
    max_output = max(128, min(context // 2, max_output))
    return EffectiveModelSettings(
        model_tag=model.ollama_tag if model else profile.model.ollama_tag,
        context_length=context,
        max_output_tokens=max_output,
        temperature=float(saved.get("temperature", profile.temperature)),
        top_p=float(saved.get("top_p", profile.top_p)),
        top_k=int(saved.get("top_k", profile.top_k)),
        repeat_penalty=float(saved.get("repeat_penalty", profile.repeat_penalty)),
        source="domain" if saved else "framework_default",
    )


def ollama_options(settings: EffectiveModelSettings) -> dict:
    return {
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "top_k": settings.top_k,
        "repeat_penalty": settings.repeat_penalty,
        "num_ctx": settings.context_length,
        "num_predict": settings.max_output_tokens,
    }


def fit_messages_to_context(messages: list[dict], context_length: int, output_reserve: int) -> list[dict]:
    """Conservatively reserve answer space by dropping oldest chat turns first.

    Exact tokenization belongs to Ollama/model templates; a three-characters-per-token estimate
    deliberately leaves headroom across languages and prevents the known prompt+answer=8K cutoff.
    """
    fitted = [dict(message) for message in messages]
    input_budget = max(256, context_length - output_reserve - 256)

    def estimate() -> int:
        return sum((len(str(item.get("content", ""))) + 2) // 3 + 8 for item in fitted)

    while len(fitted) > 2 and estimate() > input_budget:
        fitted.pop(1)
    if estimate() > input_budget and fitted and fitted[0].get("role") == "system":
        overflow_tokens = estimate() - input_budget
        content = str(fitted[0].get("content", ""))
        fitted[0]["content"] = content[: max(600, len(content) - overflow_tokens * 3)]
    return fitted
