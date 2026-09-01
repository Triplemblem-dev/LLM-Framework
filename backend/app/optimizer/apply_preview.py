"""Read-only validation for a benchmark context recommendation.

This module deliberately cannot mutate a model profile. It turns the persisted
benchmark evidence plus a fresh capability report into an exact, reviewable
model-profile change preview.
"""

from datetime import datetime, timezone
from typing import Any

from app.models import ModelProfile, OptimizationRun
from app.optimizer.activity import ActivitySnapshot
from app.optimizer.schemas import ContextApplyPreviewOut, OptimizerCapabilitiesOut
from app.optimizer.scoring import SCORE_VERSION


APPLY_PREVIEW_VERSION = "context-profile-preview-v1"
SUPPORTED_RUNNER_VERSION = "19.3-v2"
MIN_CONTEXT_LENGTH = 512
_AFFECTED_SCOPE = (
    "This model profile only. While it is active, every framework chat using this model will "
    "send the profile context to Ollama as num_ctx. Other model profiles, the embedding model, "
    "server-wide Ollama settings, and external Ollama clients are not changed."
)


def _issue(code: str, title: str, detail: str, action: str | None = None) -> dict[str, str | None]:
    return {"code": code, "title": title, "detail": detail, "action": action}


def _runtime_identity(snapshot: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not snapshot:
        return None
    cpu = snapshot.get("cpu") or {}
    return (
        snapshot.get("runtime_kind"),
        snapshot.get("os_name"),
        snapshot.get("os_release"),
        cpu.get("architecture"),
    )


def _accelerator_identity(snapshot: dict[str, Any] | None) -> tuple[tuple[Any, ...], ...] | None:
    if snapshot is None:
        return None
    return tuple(
        sorted(
            (
                str(item.get("vendor") or ""),
                str(item.get("name") or ""),
                str(item.get("compute_backend") or ""),
                str(item.get("memory_kind") or ""),
                int(item.get("memory_total_bytes") or -1),
                str(item.get("driver_version") or ""),
            )
            for item in (snapshot.get("accelerators") or [])
        )
    )


def build_context_apply_preview(
    run: OptimizationRun,
    profile: ModelProfile | None,
    report: OptimizerCapabilitiesOut,
    current_endpoint_key: str,
    current_activity: ActivitySnapshot,
    safety_ceiling: int,
    target_context_length: int | None = None,
) -> ContextApplyPreviewOut:
    """Build a fresh non-mutating preview and fail closed on stale evidence."""
    summary = run.summary or {}
    recommendation = summary.get("recommendation") or {}
    planning_limits = summary.get("planning_limits") or {}
    captured_report = run.hardware_snapshot or {}
    captured_model = captured_report.get("selected_model") or {}
    captured_runtime = captured_report.get("runtime_host")
    current_report = report.model_dump(mode="json")
    current_runtime = current_report.get("runtime_host")
    selected_model = report.selected_model
    recommended = recommendation.get("winning_context_length")
    target = target_context_length if target_context_length is not None else recommended
    current_context = profile.context_length if profile is not None else None
    blockers: list[dict[str, str | None]] = []
    warnings: list[dict[str, str | None]] = []

    if run.state != "completed":
        blockers.append(_issue(
            "run_not_completed",
            "Benchmark is not complete",
            f"This run is {run.state}; only a completed context comparison can be applied.",
            "Finish a new context comparison benchmark.",
        ))
    if run.runner_version != SUPPORTED_RUNNER_VERSION:
        blockers.append(_issue(
            "unsupported_runner_version",
            "Benchmark format is not supported",
            f"This preview expects runner {SUPPORTED_RUNNER_VERSION}, but the report uses {run.runner_version}.",
            "Run a new context comparison with the current optimizer.",
        ))
    if recommendation.get("score_version") != SCORE_VERSION:
        blockers.append(_issue(
            "stale_scoring_rule",
            "Scoring rule changed",
            "The recommendation was not produced by the optimizer's current scoring rule.",
            "Run the context comparison again before changing a setting.",
        ))
    if not isinstance(recommended, int):
        blockers.append(_issue(
            "recommendation_unavailable",
            "No usable context recommendation",
            "The completed measurements do not contain a winning context length.",
            "Keep the current setting or run another comparison.",
        ))
    winner_id = recommendation.get("winner_candidate_id")
    winner = next(
        (item for item in recommendation.get("candidate_results", []) if item.get("candidate_id") == winner_id),
        None,
    )
    if winner is None or winner.get("state") != "completed" or int(winner.get("measured_trials") or 0) < 1:
        blockers.append(_issue(
            "winner_not_measured",
            "Winning candidate lacks completed evidence",
            "The recommended candidate has no completed measured trial.",
            "Run the context comparison again.",
        ))

    if not isinstance(target, int):
        selection_kind = "unavailable"
    elif target == recommended:
        selection_kind = "recommended"
    else:
        selected_candidate = next(
            (
                item
                for item in recommendation.get("candidate_results", [])
                if item.get("context_length") == target
                and item.get("state") == "completed"
                and int(item.get("measured_trials") or 0) > 0
            ),
            None,
        )
        if selected_candidate is not None:
            selection_kind = "measured_candidate"
            warnings.append(_issue(
                "non_winning_measured_candidate",
                "You selected another measured candidate",
                f"{target:,} tokens completed benchmark measurements but was not the winning setting for this goal.",
                "Review its measured tradeoffs before applying your choice.",
            ))
        else:
            selection_kind = "custom"
            warnings.append(_issue(
                "unmeasured_context_choice",
                "This exact context was not benchmarked",
                f"{target:,} tokens is a custom choice. Its performance and processor placement were not measured by this run.",
                "Prefer a measured candidate, or accept that the custom value may perform differently.",
            ))

    if profile is None:
        blockers.append(_issue(
            "profile_missing",
            "Model profile is unavailable",
            "The saved model profile tested by this run no longer exists.",
            "Select the model again and run a new comparison.",
        ))
    elif current_context != planning_limits.get("current_profile_context"):
        blockers.append(_issue(
            "profile_context_changed",
            "Context setting changed after the benchmark",
            "The saved profile context no longer matches the setting used as the benchmark baseline.",
            "Run a new comparison from the current profile setting.",
        ))

    endpoint_status = "match" if run.endpoint_key == current_endpoint_key else "changed"
    if endpoint_status == "changed":
        blockers.append(_issue(
            "ollama_endpoint_changed",
            "Ollama endpoint changed",
            "The framework now points to a different Ollama endpoint than the benchmark used.",
            "Benchmark the model again on this endpoint.",
        ))
    if not report.ollama.reachable:
        blockers.append(_issue(
            "ollama_unreachable",
            "Ollama is not reachable",
            report.ollama.error.message if report.ollama.error else "The current Ollama endpoint did not respond.",
            report.ollama.error.action if report.ollama.error else "Start Ollama and refresh this preview.",
        ))
    if selected_model is None:
        blockers.append(_issue(
            "model_unavailable",
            "Model is not installed",
            "The benchmarked model is not currently available at this Ollama endpoint.",
            "Install the same model build or select another model and benchmark it.",
        ))

    captured_digest = captured_model.get("digest")
    current_digest = selected_model.digest if selected_model else None
    if captured_digest and current_digest:
        digest_status = "match" if captured_digest == current_digest else "changed"
        if digest_status == "changed":
            blockers.append(_issue(
                "model_build_changed",
                "Model build changed",
                "The installed model digest differs from the build that was benchmarked.",
                "Run a new comparison for the installed model build.",
            ))
    else:
        digest_status = "unavailable"
        warnings.append(_issue(
            "model_digest_unavailable",
            "Model build could not be fully verified",
            "A digest was unavailable in the saved or current Ollama evidence.",
            "Apply only if you know the model tag still refers to the same build.",
        ))

    if run.ollama_version and report.ollama.version:
        ollama_status = "match" if run.ollama_version == report.ollama.version else "changed"
        if ollama_status == "changed":
            blockers.append(_issue(
                "ollama_version_changed",
                "Ollama version changed",
                "Ollama is a different version than the one used for this benchmark.",
                "Run a new context comparison with the current Ollama version.",
            ))
    else:
        ollama_status = "unavailable"
        warnings.append(_issue(
            "ollama_version_unavailable",
            "Ollama version could not be verified",
            "The saved or current Ollama version is unavailable.",
            "Refresh after Ollama reports its version, or treat the result cautiously.",
        ))

    captured_runtime_identity = _runtime_identity(captured_runtime)
    current_runtime_identity = _runtime_identity(current_runtime)
    captured_accelerators = _accelerator_identity(captured_runtime)
    current_accelerators = _accelerator_identity(current_runtime)
    if captured_runtime_identity is None or current_runtime_identity is None:
        hardware_status = "unavailable"
        warnings.append(_issue(
            "hardware_identity_unavailable",
            "Hardware identity is incomplete",
            "The runtime hardware could not be compared with the saved benchmark evidence.",
            "Review the live device report before relying on this recommendation.",
        ))
    elif (
        captured_runtime_identity != current_runtime_identity
        or captured_accelerators != current_accelerators
    ):
        hardware_status = "changed"
        blockers.append(_issue(
            "hardware_changed",
            "Observed hardware changed",
            "The runtime platform or visible accelerator configuration differs from the benchmark.",
            "Run a new comparison on the current device.",
        ))
    elif report.ollama.hardware_visibility != "full":
        hardware_status = "partial"
        warnings.append(_issue(
            "hardware_visibility_partial",
            "Ollama hardware is only partly visible",
            "The visible runtime identity matches, but the framework cannot fully verify the device running Ollama.",
            "Review Ollama placement evidence and apply cautiously.",
        ))
    else:
        hardware_status = "match"

    native_limit = selected_model.native_context_length if selected_model else None
    if isinstance(target, int):
        if target < MIN_CONTEXT_LENGTH or target > safety_ceiling:
            blockers.append(_issue(
                "target_outside_safety_bounds",
                "Selected context is outside safety bounds",
                f"Your selection must be between {MIN_CONTEXT_LENGTH:,} and {safety_ceiling:,} tokens.",
                "Choose a value inside the displayed limits.",
            ))
        if native_limit is not None and target > native_limit:
            blockers.append(_issue(
                "target_exceeds_native_context",
                "Selected context exceeds the model limit",
                f"Your selection is larger than the model's current {native_limit:,}-token native context.",
                "Choose a value at or below the native model limit.",
            ))
        elif native_limit is None:
            warnings.append(_issue(
                "native_context_unavailable",
                "Native context limit is unavailable",
                "Ollama did not expose the model's native context limit, so only the framework safety ceiling was verified.",
                "Confirm the model's native limit before applying.",
            ))

    if current_activity.ordinary_workloads or current_activity.benchmark_run_id is not None:
        blockers.append(_issue(
            "ollama_busy",
            "Ollama is busy",
            "A chat, indexing task, or benchmark is currently using Ollama.",
            "Wait for current model work to finish, then refresh the preview.",
        ))

    confidence = str(recommendation.get("confidence") or "unavailable")
    if confidence == "unavailable":
        blockers.append(_issue(
            "confidence_unavailable",
            "Recommendation confidence is unavailable",
            "The optimizer could not establish confidence in the result.",
            "Keep the current setting or run another comparison.",
        ))
    elif confidence == "low":
        warnings.append(_issue(
            "low_confidence",
            "Recommendation confidence is low",
            "The measured evidence is usable but weak or variable.",
            "Prefer a standard-length comparison before applying.",
        ))

    no_change = (
        not blockers
        and isinstance(target, int)
        and current_context == target
    )
    if no_change:
        warnings.append(_issue(
            "already_configured",
            "Recommended context is already active",
            "The saved profile already uses the recommended context length.",
            "No setting change is needed.",
        ))
    status = "blocked" if blockers else "no_change" if no_change else "ready"

    return ContextApplyPreviewOut(
        preview_version=APPLY_PREVIEW_VERSION,
        run_id=str(run.id),
        status=status,
        can_apply=status == "ready",
        model_tag=run.model_tag,
        profile_id=str(profile.id) if profile is not None else None,
        profile_active=bool(profile and profile.is_active),
        current_context_length=current_context,
        recommended_context_length=recommended if isinstance(recommended, int) else None,
        target_context_length=target if isinstance(target, int) else None,
        selection_kind=selection_kind,
        delta_tokens=(target - current_context) if isinstance(target, int) and current_context is not None else None,
        native_context_limit=native_limit,
        safety_ceiling=safety_ceiling,
        affected_scope=_AFFECTED_SCOPE,
        blocking_reasons=blockers,
        warnings=warnings,
        checked_at=datetime.now(timezone.utc),
        evidence={
            "score_version": recommendation.get("score_version"),
            "runner_version": run.runner_version,
            "run_completed_at": run.completed_at,
            "measured_trials": int(summary.get("measured_trials") or 0),
            "confidence": confidence,
            "endpoint_status": endpoint_status,
            "model_digest_status": digest_status,
            "ollama_version_status": ollama_status,
            "hardware_status": hardware_status,
            "hardware_visibility": report.ollama.hardware_visibility,
        },
    )
