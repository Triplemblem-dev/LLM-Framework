"""Transactional per-profile context application and rollback.

Only the measured context value can be applied. This module never changes
Ollama server-global configuration and never executes host commands.
"""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Model, ModelProfile, OptimizationContextAudit, OptimizationRun
from app.optimizer import activity
from app.optimizer.apply_preview import build_context_apply_preview
from app.optimizer.discovery import discover_capabilities
from app.optimizer.schemas import (
    ContextApplyPreviewOut,
    ContextApplyRequest,
    ContextRollbackRequest,
)


class ContextChangeConflict(RuntimeError):
    pass


class ContextChangeVerificationError(RuntimeError):
    pass


def _profile_for_model(db: Session, model_tag: str, *, lock: bool = False) -> ModelProfile | None:
    query = (
        db.query(ModelProfile)
        .join(Model, Model.id == ModelProfile.model_id)
        .filter(Model.ollama_tag == model_tag)
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def fresh_preview(
    db: Session,
    run: OptimizationRun,
    target_context_length: int | None = None,
) -> ContextApplyPreviewOut:
    report = discover_capabilities(run.model_tag)
    endpoint_key = hashlib.sha256(settings.ollama_host.rstrip("/").encode("utf-8")).hexdigest()
    return build_context_apply_preview(
        run=run,
        profile=_profile_for_model(db, run.model_tag),
        report=report,
        current_endpoint_key=endpoint_key,
        current_activity=activity.snapshot(),
        safety_ceiling=settings.optimizer_context_ceiling,
        target_context_length=target_context_length,
    )


def _verify_profile_context(db: Session, profile_id: uuid.UUID, expected: int) -> bool:
    value = db.execute(
        select(ModelProfile.context_length).where(ModelProfile.id == profile_id)
    ).scalar_one()
    return value == expected


def apply_recommendation(
    db: Session,
    run: OptimizationRun,
    user_id: uuid.UUID,
    request: ContextApplyRequest,
) -> tuple[OptimizationContextAudit, bool]:
    preview = fresh_preview(db, run, request.target_context_length)
    if not preview.can_apply:
        reasons = "; ".join(item.title for item in preview.blocking_reasons) or preview.status
        raise ContextChangeConflict(f"The recommendation cannot be applied: {reasons}.")
    if request.preview_version != preview.preview_version:
        raise ContextChangeConflict("The setting preview version changed. Refresh the preview.")
    if request.expected_current_context_length != preview.current_context_length:
        raise ContextChangeConflict("The saved context changed. Refresh the preview before applying.")
    if request.target_context_length != preview.target_context_length:
        raise ContextChangeConflict("The selected context changed. Refresh the preview before applying.")
    warning_codes = {item.code for item in preview.warnings}
    acknowledged = set(request.acknowledged_warning_codes)
    if not warning_codes.issubset(acknowledged):
        raise ContextChangeConflict("Acknowledge every current preview warning before applying.")

    profile = _profile_for_model(db, run.model_tag, lock=True)
    if profile is None or profile.context_length != request.expected_current_context_length:
        db.rollback()
        raise ContextChangeConflict("The profile changed while applying. Nothing was changed.")

    audit = OptimizationContextAudit(
        user_id=user_id,
        run_id=run.id,
        profile_id=profile.id,
        model_tag=run.model_tag,
        action="apply",
        previous_context_length=profile.context_length,
        new_context_length=request.target_context_length,
        effective_context_length=request.target_context_length,
        preview_version=preview.preview_version,
        score_version=preview.evidence.score_version,
        runner_version=run.runner_version,
        acknowledged_warning_codes=sorted(warning_codes),
    )
    db.add(audit)
    db.flush()  # record previous/effective values before mutating the profile
    profile.context_length = request.target_context_length
    db.flush()
    if not _verify_profile_context(db, profile.id, request.target_context_length):
        db.rollback()
        raise ContextChangeVerificationError("Effective context verification failed; the change was rolled back.")
    active = profile.is_active
    db.commit()
    db.refresh(audit)
    return audit, active


def rollback_change(
    db: Session,
    source: OptimizationContextAudit,
    user_id: uuid.UUID,
    request: ContextRollbackRequest,
) -> tuple[OptimizationContextAudit, bool]:
    if source.action != "apply":
        raise ContextChangeConflict("Only an applied context change can be rolled back.")
    existing = db.query(OptimizationContextAudit).filter_by(source_audit_id=source.id).one_or_none()
    if existing is not None:
        profile = _profile_for_model(db, existing.model_tag)
        return existing, bool(profile and profile.is_active)

    profile = _profile_for_model(db, source.model_tag, lock=True)
    if profile is None:
        db.rollback()
        raise ContextChangeConflict("The model profile no longer exists.")
    if (
        profile.context_length != request.expected_current_context_length
        or profile.context_length != source.new_context_length
    ):
        db.rollback()
        raise ContextChangeConflict(
            "The profile changed after this apply. Refresh audit history instead of overwriting the newer value."
        )

    audit = OptimizationContextAudit(
        user_id=user_id,
        run_id=source.run_id,
        profile_id=profile.id,
        source_audit_id=source.id,
        model_tag=source.model_tag,
        action="rollback",
        previous_context_length=profile.context_length,
        new_context_length=source.previous_context_length,
        effective_context_length=source.previous_context_length,
        preview_version=source.preview_version,
        score_version=source.score_version,
        runner_version=source.runner_version,
        acknowledged_warning_codes=[],
    )
    db.add(audit)
    db.flush()
    profile.context_length = source.previous_context_length
    db.flush()
    if not _verify_profile_context(db, profile.id, source.previous_context_length):
        db.rollback()
        raise ContextChangeVerificationError("Rollback verification failed; the profile change was not committed.")
    active = profile.is_active
    db.commit()
    db.refresh(audit)
    return audit, active


def rollback_available(db: Session, audit: OptimizationContextAudit) -> bool:
    if audit.action != "apply":
        return False
    if db.query(OptimizationContextAudit).filter_by(source_audit_id=audit.id).first() is not None:
        return False
    profile = _profile_for_model(db, audit.model_tag)
    return bool(profile and profile.context_length == audit.new_context_length)
