"""Persistent optimizer benchmark orchestration and restart recovery."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from statistics import median
import threading
import time
import uuid

import httpx
from sqlalchemy.orm import Session, object_session

from app.config import settings
from app.db import SessionLocal
from app.models import OptimizationCandidate, OptimizationMeasurement, OptimizationRun
from app.optimizer import activity
from app.optimizer.adapters import inspect_runtime_host
from app.optimizer.benchmark import BenchmarkCancelled, TrialResult, run_streamed_trial
from app.optimizer.discovery import discover_capabilities
from app.optimizer.ollama_probe import probe_ollama
from app.optimizer.scoring import CandidateEvidence, score_candidates
from app.optimizer.workloads import (
    MAX_RUN_SECONDS,
    WORKLOAD_CONTEXT_NEED,
    measured_trial_count,
    trial_plan,
)

logger = logging.getLogger(__name__)

ACTIVE_STATES = {"queued", "detecting", "warming", "measuring", "evaluating"}
TERMINAL_STATES = {"completed", "cancelled", "failed"}
ALLOWED_TRANSITIONS = {
    "planned": {"queued", "cancelled"},
    "queued": {"detecting", "cancelled", "failed"},
    "detecting": {"warming", "cancelled", "failed"},
    "warming": {"measuring", "cancelled", "failed"},
    "measuring": {"warming", "evaluating", "cancelled", "failed"},
    "evaluating": {"completed", "cancelled", "failed"},
    "completed": set(),
    "cancelled": set(),
    "failed": set(),
}

_threads_lock = threading.Lock()
_cancel_events: dict[uuid.UUID, threading.Event] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def transition(run: OptimizationRun, state: str, detail: str | None = None) -> None:
    if state == run.state:
        run.current_stage_detail = detail
        return
    if state not in ALLOWED_TRANSITIONS.get(run.state, set()):
        raise ValueError(f"Invalid optimizer transition: {run.state} -> {state}")
    run.state = state
    run.current_stage_detail = detail
    if state in TERMINAL_STATES:
        run.completed_at = utcnow()


def _safe_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, httpx.TimeoutException):
        return "ollama_timeout", "Ollama did not finish the bounded trial before its timeout."
    if isinstance(exc, httpx.ConnectError):
        return "ollama_unreachable", "The configured Ollama endpoint became unreachable during the benchmark."
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 404:
            return "model_unavailable", "Ollama could not run the selected installed model."
        try:
            response_error = exc.response.json().get("error", "")
        except (ValueError, AttributeError):
            response_error = ""
        normalized = str(response_error).lower()[:1000]
        if any(marker in normalized for marker in ("out of memory", "requires more system memory", "insufficient memory")):
            return "insufficient_memory", "The selected model could not fit in the memory available to Ollama."
        return "ollama_http_error", f"Ollama returned HTTP {exc.response.status_code} during the benchmark."
    if isinstance(exc, (ValueError, KeyError)):
        return "invalid_ollama_response", "Ollama returned incomplete or invalid streamed benchmark data."
    return "benchmark_failed", "The benchmark stopped after an unexpected local error. Check backend logs."


def _placement_snapshot(model) -> dict:
    if model is None:
        return {
            "kind": "unknown",
            "accelerator_fraction": None,
            "loaded_size_bytes": None,
            "accelerator_size_bytes": None,
            "source": "Ollama /api/ps unavailable",
        }
    return {
        "kind": model.placement,
        "accelerator_fraction": model.accelerator_fraction,
        "loaded_size_bytes": model.loaded_size_bytes,
        "accelerator_size_bytes": model.accelerator_size_bytes,
        "source": "Ollama /api/ps",
    }


def _resource_snapshot(applies_to_ollama_device: str) -> dict:
    runtime = inspect_runtime_host()
    return {
        "source": "framework runtime adapter",
        "applies_to_ollama_device": applies_to_ollama_device,
        "memory": {
            "available_bytes": runtime.memory.available_bytes,
            "swap_used_bytes": runtime.memory.swap_used_bytes,
        },
        "accelerators": [
            {
                "name": item.name,
                "backend": item.compute_backend,
                "utilization_percent": item.utilization_percent,
                "memory_used_bytes": item.memory_used_bytes,
                "power_watts": item.power_watts,
                "temperature_celsius": item.temperature_celsius,
                "source": item.source,
            }
            for item in runtime.accelerators
        ],
    }


def _set_result(measurement: OptimizationMeasurement, result: TrialResult) -> None:
    measurement.ttft_ms = result.ttft_ms
    measurement.prompt_tokens = result.prompt_tokens
    measurement.generated_tokens = result.generated_tokens
    measurement.prompt_tokens_per_second = result.prompt_tokens_per_second
    measurement.generation_tokens_per_second = result.generation_tokens_per_second
    measurement.load_duration_ms = result.load_duration_ms
    measurement.total_duration_ms = result.total_duration_ms
    measurement.wall_duration_ms = result.wall_duration_ms
    measurement.output_characters = result.output_characters
    measurement.finish_reason = result.finish_reason


def _median(measurements: list[OptimizationMeasurement], field: str) -> float | None:
    values = [getattr(item, field) for item in measurements if getattr(item, field) is not None]
    return round(float(median(values)), 2) if values else None


def summarize_candidate(candidate: OptimizationCandidate) -> dict:
    completed = [item for item in candidate.measurements if item.state == "completed"]
    measured = [item for item in completed if not item.is_warmup]
    failed = [item for item in candidate.measurements if item.state == "failed"]
    placement = completed[-1].placement if completed else None
    return {
        "measured_trials": len(measured),
        "warmup_trials": len([item for item in completed if item.is_warmup]),
        "failed_trials": len(failed),
        "medians": {
            "ttft_ms": _median(measured, "ttft_ms"),
            "prompt_tokens_per_second": _median(measured, "prompt_tokens_per_second"),
            "generation_tokens_per_second": _median(measured, "generation_tokens_per_second"),
            "total_duration_ms": _median(measured, "total_duration_ms"),
            "generated_tokens": _median(measured, "generated_tokens"),
        },
        "latest_placement": placement,
        "metric_sources": {
            "timings_and_tokens": "Ollama final streamed response; ns converted to ms and rates to tokens/s",
            "ttft": "Framework monotonic clock; ms",
            "placement": "Ollama /api/ps; bytes and accelerator fraction",
            "resources": "Allow-listed framework runtime adapter; applicability is recorded per snapshot",
            "energy": "Generated tokens divided by joules estimated from the observed accelerator power snapshot and trial wall duration; unavailable without direct power data",
        },
        "generated_text_retained": False,
        "settings_changed": False,
    }


def _candidate_evidence(
    candidate: OptimizationCandidate,
    mode: str,
    benchmark_kind: str,
) -> CandidateEvidence:
    measured = [
        item for item in candidate.measurements if item.state == "completed" and not item.is_warmup
    ]
    failed = next((item for item in reversed(candidate.measurements) if item.state == "failed"), None)
    placement = next(
        (item.placement for item in reversed(candidate.measurements) if item.placement),
        None,
    )
    power_values = []
    efficiency_values = []
    workload_samples: dict[str, dict[str, list[float]]] = {}
    for measurement in measured:
        samples = workload_samples.setdefault(
            measurement.workload_case,
            {"generation_rate": [], "ttft": [], "power": []},
        )
        if measurement.generation_tokens_per_second is not None:
            samples["generation_rate"].append(measurement.generation_tokens_per_second)
        if measurement.ttft_ms is not None:
            samples["ttft"].append(measurement.ttft_ms)
        accelerators = (measurement.resource_snapshot or {}).get("accelerators") or []
        observed = [
            item.get("power_watts")
            for item in accelerators
            if isinstance(item.get("power_watts"), (int, float))
        ]
        if observed:
            power_watts = float(sum(observed))
            power_values.append(power_watts)
            samples["power"].append(power_watts)
            if (
                measurement.generated_tokens
                and measurement.wall_duration_ms
                and measurement.wall_duration_ms > 0
                and power_watts > 0
            ):
                joules = power_watts * (measurement.wall_duration_ms / 1000)
                efficiency_values.append(measurement.generated_tokens / joules)
    return CandidateEvidence(
        candidate_id=str(candidate.id),
        label=candidate.label,
        context_length=int(candidate.settings.get("num_ctx", 0)),
        is_current=bool(candidate.settings.get("is_current", len(candidate.run.candidates) == 1)),
        state=candidate.state,
        expected_measured_trials=measured_trial_count(mode, benchmark_kind),
        ttft_values=tuple(item.ttft_ms for item in measured if item.ttft_ms is not None),
        generation_rate_values=tuple(
            item.generation_tokens_per_second
            for item in measured
            if item.generation_tokens_per_second is not None
        ),
        prompt_rate_values=tuple(
            item.prompt_tokens_per_second
            for item in measured
            if item.prompt_tokens_per_second is not None
        ),
        total_latency_values=tuple(
            item.total_duration_ms for item in measured if item.total_duration_ms is not None
        ),
        generated_token_values=tuple(
            item.generated_tokens for item in measured if item.generated_tokens is not None
        ),
        power_watt_values=tuple(power_values),
        tokens_per_joule_values=tuple(efficiency_values),
        placement=placement,
        workload_samples={
            workload: {metric: tuple(values) for metric, values in metrics.items()}
            for workload, metrics in workload_samples.items()
        },
        error_code=failed.error_code if failed else None,
        error_message=failed.error_message if failed else None,
        stop_reason=candidate.settings.get("stop_reason"),
    )


def summarize_run(run: OptimizationRun) -> dict:
    session = object_session(run)
    if session is not None:
        session.flush()
        for candidate in run.candidates:
            session.expire(candidate, ["measurements"])
    previous = run.summary or {}
    candidate_summaries = {
        str(candidate.id): summarize_candidate(candidate) for candidate in run.candidates
    }
    hardware = run.hardware_snapshot or {}
    ollama = hardware.get("ollama") or {}
    benchmark_kind = previous.get("benchmark_kind", "baseline")
    recommendation = score_candidates(
        [_candidate_evidence(candidate, run.mode, benchmark_kind) for candidate in run.candidates],
        run.objective,
        WORKLOAD_CONTEXT_NEED,
        str(ollama.get("hardware_visibility") or "unknown"),
    )
    winner_id = recommendation.get("winner_candidate_id")
    winner_summary = candidate_summaries.get(winner_id) or (
        next(iter(candidate_summaries.values())) if candidate_summaries else {}
    )
    return {
        **{
            key: value
            for key, value in previous.items()
            if key
            in {
                "benchmark_kind",
                "planned_candidate_count",
                "planning_limits",
                "compatibility_at_plan",
                "candidate_ordering",
                "workload_context_need",
            }
        },
        "measured_trials": sum(item.get("measured_trials", 0) for item in candidate_summaries.values()),
        "warmup_trials": sum(item.get("warmup_trials", 0) for item in candidate_summaries.values()),
        "failed_trials": sum(item.get("failed_trials", 0) for item in candidate_summaries.values()),
        "medians": winner_summary.get("medians"),
        "latest_placement": winner_summary.get("latest_placement"),
        "candidate_summaries": candidate_summaries,
        "recommendation": recommendation,
        "recommendation_evaluated_at": utcnow().isoformat(),
        "metric_sources": winner_summary.get("metric_sources", {}),
        "generated_text_retained": False,
        "settings_changed": False,
    }


def _cancelled(db: Session, run: OptimizationRun, event: threading.Event) -> bool:
    db.refresh(run, attribute_names=["cancel_requested"])
    return event.is_set() or run.cancel_requested


def _finish_cancelled(db: Session, run: OptimizationRun) -> None:
    for candidate in run.candidates:
        if candidate.state == "running":
            candidate.state = "cancelled"
    run.summary = summarize_run(run)
    transition(run, "cancelled", "Stopped safely; completed measurements remain available.")
    db.commit()


def _last_placement(candidate: OptimizationCandidate) -> dict | None:
    return next(
        (item.placement for item in reversed(candidate.measurements) if item.state == "completed" and item.placement),
        None,
    )


def _median_generation(candidate: OptimizationCandidate) -> float | None:
    values = [
        item.generation_tokens_per_second
        for item in candidate.measurements
        if item.state == "completed" and not item.is_warmup and item.generation_tokens_per_second is not None
    ]
    return float(median(values)) if values else None


def _boundary_reason(
    candidate: OptimizationCandidate,
    reference_accelerator_fraction: float | None,
    reference_generation_rate: float | None,
    objective: str,
) -> str | None:
    measured = [
        item for item in candidate.measurements if item.state == "completed" and not item.is_warmup
    ]
    fractions = [
        float(item.placement["accelerator_fraction"])
        for item in measured
        if item.placement and isinstance(item.placement.get("accelerator_fraction"), (int, float))
    ]
    kinds = [item.placement.get("kind") for item in measured if item.placement]
    if (
        len(fractions) >= 2
        and reference_accelerator_fraction is not None
        and max(fractions) <= reference_accelerator_fraction - 0.25
    ) or (
        len(kinds) >= 2
        and reference_accelerator_fraction is not None
        and reference_accelerator_fraction > 0.25
        and all(kind == "cpu" for kind in kinds)
    ):
        return "Repeated CPU offload increased at this context, so larger candidates were not attempted."
    rate = _median_generation(candidate)
    threshold = 0.75 if objective == "fast_response" else 0.60
    if reference_generation_rate and rate is not None and rate < reference_generation_rate * threshold:
        return "Generation efficiency fell beyond the objective-specific boundary, so larger candidates were not attempted."
    return None


def _skip_remaining(candidates: list[OptimizationCandidate], start: int, reason: str) -> None:
    for candidate in candidates[start:]:
        if candidate.state == "pending":
            candidate.state = "skipped"
            candidate.settings = {**candidate.settings, "stop_reason": reason}


def execute_run(run_id: uuid.UUID, event: threading.Event) -> None:
    if not activity.try_acquire_benchmark(run_id):
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is not None and run.state in ACTIVE_STATES:
                run.error_code = "ollama_busy"
                run.error_message = "Chat, indexing, or another benchmark is currently using Ollama."
                transition(run, "failed", "Ollama was busy before the benchmark could begin.")
                db.commit()
        return

    try:
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is None or run.state not in ACTIVE_STATES:
                return
            if _cancelled(db, run, event):
                _finish_cancelled(db, run)
                return

            transition(run, "detecting", "Refreshing device, Ollama, and selected-model evidence.")
            db.commit()
            report = discover_capabilities(run.model_tag)
            run = db.get(OptimizationRun, run_id)
            run.hardware_snapshot = report.model_dump(mode="json")
            run.ollama_version = report.ollama.version
            if not report.ollama.reachable:
                run.error_code = report.ollama.error.code if report.ollama.error else "ollama_unreachable"
                run.error_message = report.ollama.error.message if report.ollama.error else "Ollama is unreachable."
                run.summary = summarize_run(run)
                transition(run, "failed", "Detection could not reach Ollama.")
                db.commit()
                return
            if report.selected_model is None:
                run.error_code = "model_unavailable"
                run.error_message = "The selected model is no longer installed in Ollama."
                run.summary = summarize_run(run)
                transition(run, "failed", "The target model was unavailable during detection.")
                db.commit()
                return

            benchmark_kind = (run.summary or {}).get("benchmark_kind", "baseline")
            plan = trial_plan(run.mode, benchmark_kind)
            candidates = list(run.candidates)
            run.total_trials = len(plan) * len(candidates)
            run.summary = {
                **(run.summary or {}),
                "candidate_ordering": "Conservative ascending context order; safety boundaries take priority over randomization.",
            }
            db.commit()
            started_monotonic = time.monotonic()
            reference_accelerator_fraction: float | None = None
            reference_generation_rate: float | None = None
            fatal_error: tuple[str, str] | None = None

            for candidate_index, candidate in enumerate(candidates):
                run = db.get(OptimizationRun, run_id)
                candidate = db.get(OptimizationCandidate, candidate.id)
                if _cancelled(db, run, event):
                    _finish_cancelled(db, run)
                    return
                candidate.state = "running"
                db.commit()

                candidate_failed = False
                boundary_failure = False
                for trial_index, (is_warmup, workload) in enumerate(plan):
                    run = db.get(OptimizationRun, run_id)
                    candidate = db.get(OptimizationCandidate, candidate.id)
                    if _cancelled(db, run, event):
                        _finish_cancelled(db, run)
                        return
                    if time.monotonic() - started_monotonic > MAX_RUN_SECONDS:
                        raise TimeoutError("run duration bound reached")

                    stage = "warming" if is_warmup else "measuring"
                    transition(
                        run,
                        stage,
                        (
                            f"Candidate {candidate_index + 1} of {len(candidates)} · {candidate.label} · "
                            f"{'warm-up' if is_warmup else 'measured'} trial {trial_index + 1} of {len(plan)} · "
                            f"{workload.key}"
                        ),
                    )
                    before = probe_ollama(
                        settings.ollama_host, report.runtime_host.runtime_kind, run.model_tag
                    )
                    measurement = OptimizationMeasurement(
                        candidate_id=candidate.id,
                        trial_index=trial_index,
                        workload_case=workload.key,
                        is_warmup=is_warmup,
                        cold_load=not bool(before.selected_model and before.selected_model.loaded),
                        state="running",
                        started_at=utcnow(),
                    )
                    db.add(measurement)
                    db.commit()

                    try:
                        result = run_streamed_trial(
                            settings.ollama_host,
                            run.model_tag,
                            workload.prompt,
                            candidate.settings,
                            event,
                        )
                    except BenchmarkCancelled:
                        measurement = db.get(OptimizationMeasurement, measurement.id)
                        measurement.state = "cancelled"
                        measurement.error_code = "cancelled_by_user"
                        measurement.error_message = "This trial was interrupted by a cancellation request."
                        measurement.completed_at = utcnow()
                        db.commit()
                        run = db.get(OptimizationRun, run_id)
                        _finish_cancelled(db, run)
                        return
                    except Exception as exc:  # noqa: BLE001 - durable safe failure output is required
                        logger.exception("Optimizer trial failed for run %s candidate %s", run_id, candidate.id)
                        code, message = _safe_error(exc)
                        measurement = db.get(OptimizationMeasurement, measurement.id)
                        measurement.state = "failed"
                        measurement.error_code = code
                        measurement.error_message = message
                        measurement.completed_at = utcnow()
                        candidate = db.get(OptimizationCandidate, candidate.id)
                        candidate.state = "failed"
                        run = db.get(OptimizationRun, run_id)
                        run.completed_trials += 1
                        db.commit()
                        candidate_failed = True
                        if code in {"insufficient_memory", "ollama_timeout"}:
                            reason = (
                                "A memory or timeout boundary was reached, so larger context candidates were not attempted."
                            )
                            candidate.settings = {**candidate.settings, "stop_reason": reason}
                            _skip_remaining(candidates, candidate_index + 1, reason)
                            boundary_failure = True
                            db.commit()
                        elif code in {"ollama_unreachable", "model_unavailable"}:
                            fatal_error = (code, message)
                        break

                    after = probe_ollama(
                        settings.ollama_host, report.runtime_host.runtime_kind, run.model_tag
                    )
                    measurement = db.get(OptimizationMeasurement, measurement.id)
                    _set_result(measurement, result)
                    measurement.placement = _placement_snapshot(after.selected_model)
                    measurement.resource_snapshot = _resource_snapshot(
                        report.runtime_host.applies_to_ollama_device
                    )
                    measurement.state = "completed"
                    measurement.completed_at = utcnow()
                    run = db.get(OptimizationRun, run_id)
                    run.completed_trials += 1
                    run.summary = summarize_run(run)
                    db.commit()

                if fatal_error:
                    break
                if candidate_failed:
                    if boundary_failure:
                        break
                    continue

                candidate = db.get(OptimizationCandidate, candidate.id)
                candidate.state = "completed"
                run = db.get(OptimizationRun, run_id)
                run.summary = summarize_run(run)
                placement = _last_placement(candidate)
                fraction = placement.get("accelerator_fraction") if placement else None
                rate = _median_generation(candidate)
                if reference_accelerator_fraction is None and isinstance(fraction, (int, float)):
                    reference_accelerator_fraction = float(fraction)
                if reference_generation_rate is None and rate is not None:
                    reference_generation_rate = rate
                reason = _boundary_reason(
                    candidate,
                    reference_accelerator_fraction,
                    reference_generation_rate,
                    run.objective,
                )
                if reason and candidate_index + 1 < len(candidates):
                    candidate.settings = {**candidate.settings, "stop_reason": reason}
                    _skip_remaining(candidates, candidate_index + 1, reason)
                    db.commit()
                    break
                db.commit()

            run = db.get(OptimizationRun, run_id)
            transition(run, "evaluating", "Calculating objective scores, Pareto tradeoffs, and confidence.")
            db.commit()
            run = db.get(OptimizationRun, run_id)
            run.summary = summarize_run(run)
            completed_candidates = [item for item in run.candidates if item.state == "completed"]
            if fatal_error:
                run.error_code, run.error_message = fatal_error
                transition(
                    run,
                    "failed",
                    "Ollama became unavailable after partial measurements were preserved.",
                )
            elif not completed_candidates:
                code, message = fatal_error or (
                    "no_candidate_completed",
                    "No context candidate completed enough measurements for a recommendation.",
                )
                run.error_code = code
                run.error_message = message
                transition(run, "failed", "No candidate produced a usable measured result.")
            else:
                transition(
                    run,
                    "completed",
                    "Context comparison complete. The recommendation changed no saved setting.",
                )
            db.commit()
    except TimeoutError:
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is not None and run.state in ACTIVE_STATES:
                for candidate in run.candidates:
                    if candidate.state == "running":
                        candidate.state = "failed"
                    elif candidate.state == "pending":
                        candidate.state = "skipped"
                        candidate.settings = {
                            **candidate.settings,
                            "stop_reason": "The total run-duration safety limit was reached.",
                        }
                run.error_code = "run_time_limit"
                run.error_message = "The benchmark reached its 30-minute safety limit."
                run.summary = summarize_run(run)
                transition(run, "failed", "The total run-duration bound was reached.")
                db.commit()
    except Exception:  # noqa: BLE001 - prevent a silent orphaned background run
        logger.exception("Optimizer run failed unexpectedly: %s", run_id)
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is not None and run.state in ACTIVE_STATES:
                for candidate in run.candidates:
                    if candidate.state == "running":
                        candidate.state = "failed"
                run.error_code = "benchmark_failed"
                run.error_message = "The benchmark stopped after an unexpected local error. Check backend logs."
                run.summary = summarize_run(run)
                transition(run, "failed", "The background benchmark stopped unexpectedly.")
                db.commit()
    finally:
        activity.release_benchmark(run_id)
        with _threads_lock:
            _cancel_events.pop(run_id, None)


def launch(run_id: uuid.UUID) -> None:
    with _threads_lock:
        if run_id in _cancel_events:
            return
        event = threading.Event()
        _cancel_events[run_id] = event
    threading.Thread(
        target=execute_run,
        args=(run_id, event),
        name=f"optimizer-{str(run_id)[:8]}",
        daemon=True,
    ).start()


def signal_cancel(run_id: uuid.UUID) -> None:
    with _threads_lock:
        event = _cancel_events.get(run_id)
    if event is not None:
        event.set()


def recover_interrupted_runs() -> int:
    """Turn jobs orphaned by a backend restart into durable partial failures."""
    with SessionLocal() as db:
        runs = db.query(OptimizationRun).filter(OptimizationRun.state.in_(ACTIVE_STATES)).all()
        for run in runs:
            for candidate in run.candidates:
                if candidate.state == "running":
                    candidate.state = "failed"
                elif candidate.state == "pending":
                    candidate.state = "skipped"
                    candidate.settings = {
                        **candidate.settings,
                        "stop_reason": "The backend restarted before this candidate ran.",
                    }
            run.summary = summarize_run(run)
            run.error_code = "backend_restarted"
            run.error_message = "The backend restarted before this benchmark finished. Partial measurements were preserved."
            run.state = "failed"
            run.current_stage_detail = "Interrupted by backend restart; start a new run to continue."
            run.completed_at = utcnow()
        db.commit()
        return len(runs)
