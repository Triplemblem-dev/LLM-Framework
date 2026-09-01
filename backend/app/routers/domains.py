import logging
import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.domain_model_settings import effective_model_settings
from app.models import Conversation, Domain, Model, ModelProfile
from app.ollama_client import list_installed_models
from app.optimizer.discovery import discover_capabilities
from app.prompt_assembly import ADVANCED_LAYER_KEYS, OWNER_CONTROLLED_LAYER_KEYS, assemble, log_scope_access
from app.schemas import (
    DomainCreate,
    DomainModelSettingsOut,
    DomainModelSettingsUpdate,
    DomainTreeOut,
    DomainUpdate,
    PromptLayer,
    PromptLayerControlOut,
    PromptLayerControlUpdate,
    PromptPreviewOut,
    SubDomainOut,
)

router = APIRouter(prefix="/domains", tags=["domains"], dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-")
    return slug or "scope"


def unique_slug(db: Session, user_id: uuid.UUID, parent_domain_id: uuid.UUID | None, name: str) -> str:
    base = slugify(name)
    slug = base
    suffix = 2
    while (
        db.query(Domain)
        .filter_by(user_id=user_id, parent_domain_id=parent_domain_id, slug=slug)
        .first()
        is not None
    ):
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def get_domain_or_404(db: Session, domain_id: uuid.UUID) -> Domain:
    domain = db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return domain


def get_owned_domain_or_404(db: Session, domain_id: uuid.UUID, user_id: uuid.UUID) -> Domain:
    """Resolve ownership on the server; a browser-supplied scope id is never sufficient."""
    domain = db.query(Domain).filter_by(id=domain_id, user_id=user_id).one_or_none()
    if domain is None:
        # Do not reveal whether an id exists for another owner.
        raise HTTPException(status_code=404, detail="Domain not found")
    return domain


def _domain_model_settings_out(db: Session, scope: Domain) -> DomainModelSettingsOut:
    effective = effective_model_settings(db, scope)
    if effective is None:
        raise HTTPException(status_code=400, detail="No model is selected")
    native = None
    allocated = None
    try:
        report = discover_capabilities(effective.model_tag)
        if report.selected_model is not None:
            native = report.selected_model.native_context_length
            allocated = report.selected_model.allocated_context_length
    except Exception:  # hardware discovery is advisory; settings remain usable without it
        pass
    ceiling = min(native or 262_144, 262_144)
    if allocated:
        recommended = min(allocated, ceiling)
        basis = "Detected from this model's current Ollama allocation on this hardware."
    else:
        recommended = min(effective.context_length, ceiling)
        basis = "Conservative current setting; load the model and refresh for a hardware-detected option."
    return DomainModelSettingsOut(
        domain_id=scope.id,
        model_tag=effective.model_tag,
        context_length=effective.context_length,
        max_output_tokens=effective.max_output_tokens,
        temperature=effective.temperature,
        top_p=effective.top_p,
        top_k=effective.top_k,
        repeat_penalty=effective.repeat_penalty,
        source=effective.source,
        native_context_length=native,
        detected_allocated_context_length=allocated,
        recommended_context_length=recommended,
        recommendation_basis=basis,
    )


def _owned_descendant_ids(db: Session, root: Domain) -> list[uuid.UUID]:
    """Return root + descendants and refuse inconsistent cross-owner parent links.

    v1 only permits one child level, but walking breadth-first makes the destructive path safe
    if hierarchy depth is expanded later without silently changing cascade behavior.
    """
    result = [root.id]
    frontier = [root.id]
    while frontier:
        children = db.query(Domain.id, Domain.user_id).filter(Domain.parent_domain_id.in_(frontier)).all()
        if any(child.user_id != root.user_id for child in children):
            raise HTTPException(
                status_code=409,
                detail="Scope ownership is inconsistent; deletion was refused",
            )
        frontier = [child.id for child in children]
        result.extend(frontier)
    return result


def _stage_scope_storage(scope_ids: list[uuid.UUID]) -> list[tuple[Path, Path]]:
    """Atomically move scope document directories aside before the database transaction.

    A failed database commit can restore the directories. After a successful commit, the staged
    files are removed. Symlinks and paths outside the configured storage root are rejected.
    """
    root = Path(settings.document_storage_path).resolve()
    if not root.exists():
        return []
    if not root.is_dir():
        raise HTTPException(status_code=500, detail="Document storage root is invalid")

    deleting_root = root / ".deleting"
    if deleting_root.is_symlink():
        raise HTTPException(status_code=500, detail="Document deletion staging path is invalid")
    deleting_root.mkdir(exist_ok=True)

    moved: list[tuple[Path, Path]] = []
    try:
        for scope_id in scope_ids:
            source = root / str(scope_id)
            if source.is_symlink():
                raise HTTPException(status_code=500, detail="Unsafe document storage path")
            if not source.exists():
                continue
            resolved_source = source.resolve()
            if resolved_source.parent != root or not resolved_source.is_dir():
                raise HTTPException(status_code=500, detail="Unsafe document storage path")
            staged = deleting_root / f"{scope_id}-{uuid.uuid4().hex}"
            source.replace(staged)
            moved.append((source, staged))
    except Exception:
        for source, staged in reversed(moved):
            if staged.exists() and not source.exists():
                staged.replace(source)
        raise
    return moved


def _restore_staged_storage(moved: list[tuple[Path, Path]]) -> None:
    for source, staged in reversed(moved):
        if staged.exists() and not source.exists():
            staged.replace(source)


def _remove_staged_storage(moved: list[tuple[Path, Path]]) -> bool:
    complete = True
    for _source, staged in moved:
        try:
            shutil.rmtree(staged)
        except OSError:
            complete = False
            logger.exception("Could not remove staged document directory %s", staged)
    return complete


@router.get("", response_model=list[DomainTreeOut])
def list_domains(db: Session = Depends(get_db)):
    user = get_current_user(db)
    top_level = (
        db.query(Domain)
        .filter_by(user_id=user.id, parent_domain_id=None)
        .order_by(Domain.created_at)
        .all()
    )
    return top_level


@router.get("/{domain_id}/model-settings", response_model=DomainModelSettingsOut)
def get_domain_model_settings(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    return _domain_model_settings_out(db, scope)


@router.put("/{domain_id}/model-settings", response_model=DomainModelSettingsOut)
def update_domain_model_settings(
    domain_id: uuid.UUID,
    body: DomainModelSettingsUpdate,
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    if body.max_output_tokens > body.context_length // 2:
        raise HTTPException(status_code=400, detail="Answer length must be at most half of the context window")
    try:
        installed = {item["model"]: item for item in list_installed_models()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Ollama: {exc}") from exc
    if body.model_tag not in installed:
        raise HTTPException(status_code=400, detail=f"'{body.model_tag}' is not installed in Ollama")
    model = db.query(Model).filter_by(ollama_tag=body.model_tag).one_or_none()
    if model is None:
        info = installed[body.model_tag]
        details = info.get("details", {})
        model = Model(
            name=info["name"],
            ollama_tag=body.model_tag,
            architecture=details.get("family"),
            parameter_count=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            file_size_bytes=info.get("size"),
        )
        db.add(model)
        db.flush()
        db.add(ModelProfile(model_id=model.id))
    scope.model_settings = body.model_dump()
    db.commit()
    db.refresh(scope)
    return _domain_model_settings_out(db, scope)


@router.post("", response_model=DomainTreeOut)
def create_domain(body: DomainCreate, db: Session = Depends(get_db)):
    user = get_current_user(db)
    domain = Domain(
        user_id=user.id,
        parent_domain_id=None,
        name=body.name,
        slug=unique_slug(db, user.id, None, body.name),
        description=body.description,
        scope_prompt=body.prompt,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


@router.post("/{domain_id}/subdomains", response_model=SubDomainOut)
def create_subdomain(domain_id: uuid.UUID, body: DomainCreate, db: Session = Depends(get_db)):
    user = get_current_user(db)
    parent = get_owned_domain_or_404(db, domain_id, user.id)
    if parent.parent_domain_id is not None:
        raise HTTPException(
            status_code=400, detail="Cannot create a sub-domain under a sub-domain (v1 supports two levels only)"
        )
    sub = Domain(
        user_id=user.id,
        parent_domain_id=parent.id,
        name=body.name,
        slug=unique_slug(db, user.id, parent.id, body.name),
        description=body.description,
        scope_prompt=body.prompt,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.patch("/{domain_id}", response_model=SubDomainOut)
def update_domain(domain_id: uuid.UUID, body: DomainUpdate, db: Session = Depends(get_db)):
    user = get_current_user(db)
    domain = get_owned_domain_or_404(db, domain_id, user.id)
    if body.name is not None:
        domain.name = body.name
    if body.description is not None:
        domain.description = body.description
    if body.prompt is not None:
        domain.scope_prompt = body.prompt
    if body.inheritance is not None:
        domain.inheritance = body.inheritance
    if body.share_with_siblings is not None:
        domain.share_with_siblings = body.share_with_siblings
    db.commit()
    db.refresh(domain)
    return domain


@router.put("/{domain_id}/prompt-layers/{layer_key}", response_model=PromptLayerControlOut)
def update_prompt_layer_control(
    domain_id: uuid.UUID,
    layer_key: str,
    body: PromptLayerControlUpdate,
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    domain = get_owned_domain_or_404(db, domain_id, user.id)
    if layer_key not in OWNER_CONTROLLED_LAYER_KEYS:
        raise HTTPException(status_code=400, detail="This prompt layer cannot be controlled")
    if layer_key in ADVANCED_LAYER_KEYS and not body.enabled and not body.risk_acknowledged:
        raise HTTPException(
            status_code=400,
            detail="Risk acknowledgement is required before an advanced prompt rule is disabled",
        )

    overrides = dict(domain.prompt_layer_overrides or {})
    if body.enabled:
        overrides.pop(layer_key, None)
    else:
        overrides[layer_key] = False
    domain.prompt_layer_overrides = overrides
    db.commit()
    return PromptLayerControlOut(key=layer_key, enabled=body.enabled)


@router.get("/{domain_id}/prompt-preview", response_model=PromptPreviewOut)
def prompt_preview(
    domain_id: uuid.UUID,
    draft: str = "",
    conversation_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    history = []
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.domain_id == scope.id:
            history = conv.messages
    result = assemble(db, scope, history, draft)
    log_scope_access(db, user.id, scope, context="prompt_preview")
    return PromptPreviewOut(layers=[PromptLayer(**layer) for layer in result.layers])


@router.delete("/{domain_id}")
def delete_domain(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    domain = get_owned_domain_or_404(db, domain_id, user.id)
    scope_ids = _owned_descendant_ids(db, domain)
    moved = _stage_scope_storage(scope_ids)
    try:
        result = db.execute(
            delete(Domain).where(Domain.id == domain.id, Domain.user_id == user.id)
        )
        if result.rowcount != 1:
            raise RuntimeError("Domain disappeared during deletion")
        db.commit()
    except Exception:
        db.rollback()
        _restore_staged_storage(moved)
        raise

    storage_cleanup_complete = _remove_staged_storage(moved)
    return {
        "ok": True,
        "deleted_scope_count": len(scope_ids),
        "storage_cleanup_complete": storage_cleanup_complete,
    }
