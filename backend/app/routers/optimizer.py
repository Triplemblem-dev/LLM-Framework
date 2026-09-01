from datetime import datetime, timezone
import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import (
    Model,
    ModelProfile,
    OptimizationCandidate,
    OptimizationContextAudit,
    OptimizationRun,
)
from app.optimizer import activity
from app.optimizer.candidates import ContextCandidatePlan, context_candidates
from app.optimizer.context_apply import (
    ContextChangeConflict,
    ContextChangeVerificationError,
    apply_recommendation,
    fresh_preview,
    rollback_available,
    rollback_change,
)
from app.optimizer.discovery import discover_capabilities
from app.optimizer.export import redacted_markdown
from app.optimizer.jobs import ACTIVE_STATES, TERMINAL_STATES, launch, signal_cancel, summarize_run, transition
from app.optimizer.ollama_probe import safe_endpoint_display
from app.optimizer.schemas import (
    ContextApplyRequest,
    ContextApplyPreviewOut,
    ContextAuditOut,
    ContextChangeResultOut,
    ContextRollbackRequest,
    OptimizationRunCreate,
    OptimizationRunOut,
    OptimizerCapabilitiesOut,
)
from app.optimizer.workloads import (
    CONTEXT_WORKLOAD_VERSION,
    MAX_RESPONSE_TOKENS,
    WORKLOAD_CONTEXT_NEED,
    trial_plan,
)

router = APIRouter(
    prefix="/optimizer",
    tags=["optimizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("/capabilities", response_model=OptimizerCapabilitiesOut)
def capabilities(
    model_tag: str | None = Query(
        default=None,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$",
    ),
) -> OptimizerCapabilitiesOut:
    """Return a fresh read-only report; unreachable Ollama is report data, not a 502."""
    return discover_capabilities(model_tag)


def _run_or_404(db: Session, run_id: uuid.UUID, user_id: uuid.UUID) -> OptimizationRun:
    run = db.query(OptimizationRun).filter_by(id=run_id, user_id=user_id).one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return run


def _serialize(run: OptimizationRun) -> dict:
    candidates = []
    for candidate in run.candidates:
        candidates.append(
            {
                "id": str(candidate.id),
                "label": candidate.label,
                "settings": candidate.settings,
                "state": candidate.state,
                "measurements": [
                    {
                        "id": str(item.id),
                        "trial_index": item.trial_index,
                        "workload_case": item.workload_case,
                        "is_warmup": item.is_warmup,
                        "cold_load": item.cold_load,
                        "state": item.state,
                        "ttft_ms": item.ttft_ms,
                        "prompt_tokens": item.prompt_tokens,
                        "generated_tokens": item.generated_tokens,
                        "prompt_tokens_per_second": item.prompt_tokens_per_second,
                        "generation_tokens_per_second": item.generation_tokens_per_second,
                        "load_duration_ms": item.load_duration_ms,
                        "total_duration_ms": item.total_duration_ms,
                        "wall_duration_ms": item.wall_duration_ms,
                        "output_characters": item.output_characters,
                        "finish_reason": item.finish_reason,
                        "placement": item.placement,
                        "resource_snapshot": item.resource_snapshot,
                        "error_code": item.error_code,
                        "error_message": item.error_message,
                        "started_at": item.started_at,
                        "completed_at": item.completed_at,
                    }
                    for item in candidate.measurements
                ],
            }
        )
    return {
        "id": str(run.id),
        "model_tag": run.model_tag,
        "benchmark_kind": (run.summary or {}).get(
            "benchmark_kind", "context_comparison" if len(run.candidates) > 1 else "baseline"
        ),
        "objective": run.objective,
        "mode": run.mode,
        "workload_version": run.workload_version,
        "runner_version": run.runner_version,
        "endpoint_display": run.endpoint_display,
        "state": run.state,
        "current_stage_detail": run.current_stage_detail,
        "total_trials": run.total_trials,
        "completed_trials": run.completed_trials,
        "cancel_requested": run.cancel_requested,
        "ollama_version": run.ollama_version,
        "hardware_snapshot": run.hardware_snapshot,
        "summary": run.summary or {},
        "error_code": run.error_code,
        "error_message": run.error_message,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "estimated_seconds": (120 if run.mode == "quick" else 240) * max(1, len(run.candidates)),
        "disruption_notice": (
            "This benchmark loads the selected model and temporarily uses substantial CPU, GPU, "
            "and memory. Chat and indexing pause while it runs. It does not unload other models, "
            "restart Ollama, retain generated text, or change any saved setting."
        ),
        "candidates": candidates,
    }


def _serialize_audit(db: Session, audit: OptimizationContextAudit) -> dict:
    return {
        "id": str(audit.id),
        "run_id": str(audit.run_id) if audit.run_id else None,
        "source_audit_id": str(audit.source_audit_id) if audit.source_audit_id else None,
        "model_tag": audit.model_tag,
        "action": audit.action,
        "previous_context_length": audit.previous_context_length,
        "new_context_length": audit.new_context_length,
        "effective_context_length": audit.effective_context_length,
        "preview_version": audit.preview_version,
        "score_version": audit.score_version,
        "runner_version": audit.runner_version,
        "acknowledged_warning_codes": audit.acknowledged_warning_codes or [],
        "rollback_available": rollback_available(db, audit),
        "created_at": audit.created_at,
    }


@router.post("/runs", response_model=OptimizationRunOut, status_code=201)
def create_run(body: OptimizationRunCreate, db: Session = Depends(get_db)):
    """Create a durable reviewable plan; this endpoint does not start the model."""
    user = get_current_user(db)
    report = discover_capabilities(body.model_tag)
    if not report.ollama.reachable:
        detail = report.ollama.error.message if report.ollama.error else "Ollama is unreachable."
        raise HTTPException(status_code=409, detail=detail)
    if report.selected_model is None:
        raise HTTPException(status_code=400, detail="Select a model that is installed in Ollama.")
    if body.objective == "low_energy":
        power = next((item for item in report.capabilities if item.key == "power_metrics"), None)
        if power is None or power.status != "available":
            raise HTTPException(
                status_code=400,
                detail="Low energy cannot be measured because no trustworthy Ollama-device power sensor is available.",
            )

    native_context_limit = min(
        report.selected_model.native_context_length or settings.optimizer_context_ceiling,
        settings.optimizer_context_ceiling,
    )
    context_length = min(native_context_limit, 8192)
    profile = (
        db.query(ModelProfile)
        .join(Model, Model.id == ModelProfile.model_id)
        .filter(Model.ollama_tag == body.model_tag)
        .first()
    )
    if profile is not None:
        context_length = max(512, min(profile.context_length, native_context_limit))
    if body.benchmark_kind == "context_comparison":
        candidate_plans = context_candidates(
            context_length,
            report.selected_model.native_context_length,
            settings.optimizer_context_ceiling,
        )
    else:
        candidate_plans = [
            ContextCandidatePlan(
                context_length=context_length,
                is_current=True,
                label="Current baseline",
            )
        ]
    endpoint_key = hashlib.sha256(settings.ollama_host.rstrip("/").encode("utf-8")).hexdigest()
    plan = trial_plan(body.mode, body.benchmark_kind)
    run = OptimizationRun(
        user_id=user.id,
        model_tag=body.model_tag,
        objective=body.objective,
        mode=body.mode,
        workload_version=(
            CONTEXT_WORKLOAD_VERSION if body.benchmark_kind == "context_comparison" else "baseline-v1"
        ),
        runner_version="19.3-v2" if body.benchmark_kind == "context_comparison" else "19.2-v1",
        endpoint_key=endpoint_key,
        endpoint_display=safe_endpoint_display(settings.ollama_host),
        state="planned",
        current_stage_detail="Review the bounded synthetic benchmark before starting it.",
        total_trials=len(plan) * len(candidate_plans),
        ollama_version=report.ollama.version,
        hardware_snapshot=report.model_dump(mode="json"),
        summary={
            "benchmark_kind": body.benchmark_kind,
            "generated_text_retained": False,
            "settings_changed": False,
            "planned_candidate_count": len(candidate_plans),
            "workload_context_need": WORKLOAD_CONTEXT_NEED,
            "planning_limits": {
                "native_context_length": report.selected_model.native_context_length,
                "safety_ceiling": settings.optimizer_context_ceiling,
                "current_profile_context": context_length,
            },
            "compatibility_at_plan": {
                "model_digest": report.selected_model.digest,
                "ollama_version": report.ollama.version,
            },
        },
    )
    db.add(run)
    db.flush()
    db.add_all(
        [
            OptimizationCandidate(
                run_id=run.id,
                position=position,
                label=candidate_plan.label,
                settings={
                    "num_ctx": candidate_plan.context_length,
                    "num_predict": 96 if body.mode == "quick" else MAX_RESPONSE_TOKENS,
                    "temperature": 0,
                    "seed": 42,
                    "is_current": candidate_plan.is_current,
                    "workload_context_need": WORKLOAD_CONTEXT_NEED,
                    "native_context_limit": report.selected_model.native_context_length,
                    "safety_ceiling": settings.optimizer_context_ceiling,
                },
            )
            for position, candidate_plan in enumerate(candidate_plans)
        ]
    )
    db.commit()
    db.refresh(run)
    return _serialize(run)


@router.get("/runs", response_model=list[OptimizationRunOut])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    runs = (
        db.query(OptimizationRun)
        .filter_by(user_id=user.id)
        .order_by(OptimizationRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize(run) for run in runs]


@router.get("/runs/{run_id}", response_model=OptimizationRunOut)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    return _serialize(_run_or_404(db, run_id, user.id))


@router.get(
    "/runs/{run_id}/context-apply-preview",
    response_model=ContextApplyPreviewOut,
)
def context_apply_preview(
    run_id: uuid.UUID,
    target_context_length: int | None = Query(default=None, ge=512, le=262_144),
    db: Session = Depends(get_db),
):
    """Fresh, authenticated, read-only validation of one context recommendation."""
    user = get_current_user(db)
    run = _run_or_404(db, run_id, user.id)
    return fresh_preview(db, run, target_context_length)


@router.post(
    "/runs/{run_id}/context-apply",
    response_model=ContextChangeResultOut,
)
def apply_context(
    run_id: uuid.UUID,
    body: ContextApplyRequest,
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    run = _run_or_404(db, run_id, user.id)
    try:
        audit, profile_active = apply_recommendation(db, run, user.id, body)
    except ContextChangeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContextChangeVerificationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "verified": True,
        "profile_active": profile_active,
        "effective_context_length": audit.effective_context_length,
        "audit": _serialize_audit(db, audit),
    }


@router.get("/context-audits", response_model=list[ContextAuditOut])
def list_context_audits(
    model_tag: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    query = db.query(OptimizationContextAudit).filter_by(user_id=user.id)
    if model_tag:
        query = query.filter(OptimizationContextAudit.model_tag == model_tag)
    audits = query.order_by(OptimizationContextAudit.created_at.desc()).limit(limit).all()
    return [_serialize_audit(db, audit) for audit in audits]


@router.post(
    "/context-audits/{audit_id}/rollback",
    response_model=ContextChangeResultOut,
)
def rollback_context(
    audit_id: uuid.UUID,
    body: ContextRollbackRequest,
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    source = (
        db.query(OptimizationContextAudit)
        .filter_by(id=audit_id, user_id=user.id)
        .one_or_none()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Context audit entry not found")
    try:
        audit, profile_active = rollback_change(db, source, user.id, body)
    except ContextChangeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContextChangeVerificationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "verified": True,
        "profile_active": profile_active,
        "effective_context_length": audit.effective_context_length,
        "audit": _serialize_audit(db, audit),
    }


@router.post("/runs/{run_id}/start", response_model=OptimizationRunOut)
def start_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    run = _run_or_404(db, run_id, user.id)
    if run.state in TERMINAL_STATES or run.state in ACTIVE_STATES:
        return _serialize(run)
    if run.state != "planned":
        raise HTTPException(status_code=409, detail=f"Run cannot start from state {run.state}.")

    advisory_key = int.from_bytes(bytes.fromhex(run.endpoint_key[:16]), "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": advisory_key})
    competing = (
        db.query(OptimizationRun)
        .filter(
            OptimizationRun.id != run.id,
            OptimizationRun.endpoint_key == run.endpoint_key,
            OptimizationRun.state.in_(ACTIVE_STATES),
        )
        .first()
    )
    if competing is not None:
        raise HTTPException(
            status_code=409,
            detail="Another optimization run is already using this Ollama endpoint.",
        )
    current_activity = activity.snapshot()
    if current_activity.ordinary_workloads > 0 or current_activity.benchmark_run_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Ollama is busy with chat, indexing, or another benchmark. Wait for it to finish, then start this run.",
        )

    transition(run, "queued", "Waiting for the background benchmark worker.")
    run.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    launch(run.id)
    return _serialize(run)


@router.post("/runs/{run_id}/cancel", response_model=OptimizationRunOut)
def cancel_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    run = _run_or_404(db, run_id, user.id)
    if run.state in TERMINAL_STATES:
        return _serialize(run)
    run.cancel_requested = True
    if run.state == "planned":
        for candidate in run.candidates:
            candidate.state = "cancelled"
        run.summary = summarize_run(run)
        transition(run, "cancelled", "Cancelled before the model was started.")
    else:
        run.current_stage_detail = "Cancellation requested; stopping at the current safe point."
    db.commit()
    signal_cancel(run.id)
    db.refresh(run)
    return _serialize(run)


@router.get("/runs/{run_id}/export")
def export_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    """Download a deliberately redacted Markdown copy of one owned local report."""
    user = get_current_user(db)
    run = _run_or_404(db, run_id, user.id)
    filename = f"optimizer-report-{run.created_at.date().isoformat()}.md"
    return Response(
        content=redacted_markdown(run),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    run = _run_or_404(db, run_id, user.id)
    if run.state in ACTIVE_STATES:
        raise HTTPException(status_code=409, detail="Cancel the active run before deleting its report.")
    db.delete(run)
    db.commit()
