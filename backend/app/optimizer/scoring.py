"""Versioned, deterministic optimizer scoring and Pareto analysis."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median, pstdev
from typing import Any


SCORE_VERSION = "context-objective-v2"
OBJECTIVE_WEIGHTS = {
    "balanced": {"latency": 0.20, "generation": 0.25, "memory": 0.10, "reliability": 0.15, "context": 0.10, "energy": 0.10, "placement": 0.10},
    "fast_response": {"latency": 0.30, "generation": 0.30, "memory": 0.05, "reliability": 0.10, "context": 0.05, "energy": 0.05, "placement": 0.15},
    "large_context": {"latency": 0.12, "generation": 0.15, "memory": 0.07, "reliability": 0.16, "context": 0.35, "energy": 0.05, "placement": 0.10},
    "low_memory": {"latency": 0.07, "generation": 0.10, "memory": 0.38, "reliability": 0.15, "context": 0.10, "energy": 0.05, "placement": 0.15},
    "low_energy": {"latency": 0.08, "generation": 0.10, "memory": 0.10, "reliability": 0.15, "context": 0.10, "energy": 0.40, "placement": 0.07},
}


@dataclass(frozen=True)
class CandidateEvidence:
    candidate_id: str
    label: str
    context_length: int
    is_current: bool
    state: str
    expected_measured_trials: int
    ttft_values: tuple[float, ...]
    generation_rate_values: tuple[float, ...]
    prompt_rate_values: tuple[float, ...]
    total_latency_values: tuple[float, ...]
    generated_token_values: tuple[int, ...]
    power_watt_values: tuple[float, ...]
    tokens_per_joule_values: tuple[float, ...]
    placement: dict[str, Any] | None
    workload_samples: dict[str, dict[str, tuple[float, ...]]]
    error_code: str | None = None
    error_message: str | None = None
    stop_reason: str | None = None


def _median(values: tuple[float, ...] | tuple[int, ...]) -> float | None:
    return round(float(median(values)), 2) if values else None


def _cv(values: tuple[float, ...]) -> float | None:
    if len(values) < 2 or mean(values) == 0:
        return None
    return round(pstdev(values) / mean(values), 4)


def _within_workload_variance(
    workload_samples: dict[str, dict[str, tuple[float, ...]]]
) -> tuple[dict[str, dict[str, float | None]], dict[str, float | None]]:
    per_workload: dict[str, dict[str, float | None]] = {}
    for workload, metrics in workload_samples.items():
        per_workload[workload] = {
            "generation_rate_cv": _cv(metrics.get("generation_rate", ())),
            "ttft_cv": _cv(metrics.get("ttft", ())),
            "power_cv": _cv(metrics.get("power", ())),
        }
    aggregate = {
        metric: max(
            (values[metric] for values in per_workload.values() if values[metric] is not None),
            default=None,
        )
        for metric in ("generation_rate_cv", "ttft_cv", "power_cv")
    }
    return per_workload, aggregate


def _normalize(value: float | None, values: list[float], *, higher_is_better: bool) -> float:
    if value is None or not values:
        return 0.5
    low, high = min(values), max(values)
    if high == low:
        return 1.0
    normalized = (value - low) / (high - low)
    return normalized if higher_is_better else 1 - normalized


def _placement_quality(placement: dict[str, Any] | None) -> float:
    if not placement:
        return 0.5
    kind = placement.get("kind")
    fraction = placement.get("accelerator_fraction")
    if kind == "accelerator":
        return 1.0
    if kind == "cpu":
        return 0.1
    if kind == "split" and isinstance(fraction, (int, float)):
        return max(0.1, min(1.0, float(fraction)))
    return 0.5


def _lower_is_better_value(value: Any) -> float:
    return -float(value) if isinstance(value, (int, float)) else -float("inf")


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_values = (
        _lower_is_better_value(left["medians"]["ttft_ms"]),
        left["medians"]["generation_tokens_per_second"] or 0,
        _lower_is_better_value(left["loaded_size_bytes"]),
        _lower_is_better_value(left["medians"]["power_watts"]),
        left["medians"]["tokens_per_joule"] or 0,
        left["context_length"],
        left["reliability"],
    )
    right_values = (
        _lower_is_better_value(right["medians"]["ttft_ms"]),
        right["medians"]["generation_tokens_per_second"] or 0,
        _lower_is_better_value(right["loaded_size_bytes"]),
        _lower_is_better_value(right["medians"]["power_watts"]),
        right["medians"]["tokens_per_joule"] or 0,
        right["context_length"],
        right["reliability"],
    )
    return all(a >= b for a, b in zip(left_values, right_values)) and any(
        a > b for a, b in zip(left_values, right_values)
    )


def score_candidates(
    evidence: list[CandidateEvidence],
    objective: str,
    workload_context_need: int,
    hardware_visibility: str,
) -> dict[str, Any]:
    weights = OBJECTIVE_WEIGHTS[objective]
    results: list[dict[str, Any]] = []
    for item in evidence:
        measured_count = len(item.generation_rate_values)
        per_workload_variance, aggregate_variance = _within_workload_variance(item.workload_samples)
        repetitions = [
            len(metrics.get("generation_rate", ()))
            for metrics in item.workload_samples.values()
        ]
        loaded_size = item.placement.get("loaded_size_bytes") if item.placement else None
        results.append(
            {
                "candidate_id": item.candidate_id,
                "label": item.label,
                "context_length": item.context_length,
                "is_current": item.is_current,
                "state": item.state,
                "measured_trials": measured_count,
                "expected_measured_trials": item.expected_measured_trials,
                "minimum_repetitions_per_workload": min(repetitions, default=0),
                "reliability": round(min(1.0, measured_count / max(1, item.expected_measured_trials)), 3),
                "medians": {
                    "ttft_ms": _median(item.ttft_values),
                    "generation_tokens_per_second": _median(item.generation_rate_values),
                    "prompt_tokens_per_second": _median(item.prompt_rate_values),
                    "total_duration_ms": _median(item.total_latency_values),
                    "generated_tokens": _median(item.generated_token_values),
                    "power_watts": _median(item.power_watt_values),
                    "tokens_per_joule": _median(item.tokens_per_joule_values),
                },
                "variance": {
                    **aggregate_variance,
                    "method": "maximum_within_workload_cv",
                    "by_workload": per_workload_variance,
                },
                "placement": item.placement,
                "loaded_size_bytes": loaded_size if isinstance(loaded_size, int) else None,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "stop_reason": item.stop_reason,
                "score": None,
                "dimensions": None,
            }
        )

    eligible = [item for item in results if item["state"] == "completed" and item["measured_trials"] > 0]
    ttfts = [item["medians"]["ttft_ms"] for item in eligible if item["medians"]["ttft_ms"] is not None]
    rates = [item["medians"]["generation_tokens_per_second"] for item in eligible if item["medians"]["generation_tokens_per_second"] is not None]
    sizes = [float(item["loaded_size_bytes"]) for item in eligible if item["loaded_size_bytes"] is not None]
    powers = [item["medians"]["power_watts"] for item in eligible if item["medians"]["power_watts"] is not None]
    efficiencies = [
        item["medians"]["tokens_per_joule"]
        for item in eligible
        if item["medians"]["tokens_per_joule"] is not None
    ]
    max_context = max((item["context_length"] for item in eligible), default=workload_context_need)

    for item in eligible:
        placement_quality = _placement_quality(item["placement"])
        size_quality = _normalize(
            float(item["loaded_size_bytes"]) if item["loaded_size_bytes"] is not None else None,
            sizes,
            higher_is_better=False,
        )
        workload_fit = min(1.0, item["context_length"] / max(1, workload_context_need))
        context_quality = workload_fit
        if objective == "large_context":
            context_quality = 0.65 * workload_fit + 0.35 * (item["context_length"] / max_context)
        dimensions = {
            "latency": _normalize(item["medians"]["ttft_ms"], ttfts, higher_is_better=False),
            "generation": _normalize(item["medians"]["generation_tokens_per_second"], rates, higher_is_better=True),
            "memory": size_quality,
            "reliability": item["reliability"],
            "context": context_quality,
            "energy": _normalize(
                item["medians"]["tokens_per_joule"], efficiencies, higher_is_better=True
            ) if efficiencies else _normalize(
                item["medians"]["power_watts"], powers, higher_is_better=False
            ),
            "placement": placement_quality,
        }
        item["dimensions"] = {key: round(value, 4) for key, value in dimensions.items()}
        item["score"] = round(sum(dimensions[key] * weights[key] for key in weights) * 100, 1)

    pareto = [
        item["candidate_id"]
        for item in eligible
        if not any(_dominates(other, item) for other in eligible if other is not item)
    ]
    winner = max(eligible, key=lambda item: (item["score"], -item["context_length"])) if eligible else None
    baseline = next((item for item in results if item["is_current"]), None)

    confidence_reasons: list[str] = []
    confidence = "high"
    if not eligible:
        confidence = "unavailable"
        confidence_reasons.append("No candidate completed a measured trial.")
    else:
        minimum_repetitions = min(item["minimum_repetitions_per_workload"] for item in eligible)
        cvs = [
            value
            for item in eligible
            for value in (
                item["variance"]["generation_rate_cv"],
                item["variance"]["ttft_cv"],
                item["variance"]["power_cv"],
            )
            if value is not None
        ]
        if minimum_repetitions < 3:
            confidence = "medium" if minimum_repetitions >= 2 else "low"
            confidence_reasons.append(
                f"Each workload has only {minimum_repetitions} repeated measurement(s) in the least-tested candidate."
            )
        if cvs and max(cvs) > 0.25:
            confidence = "low"
            confidence_reasons.append("Within-workload repeat variance exceeded 25%.")
        elif cvs and max(cvs) > 0.10 and confidence == "high":
            confidence = "medium"
            confidence_reasons.append("Within-workload repeat variance exceeded 10%.")
        if hardware_visibility != "full":
            if confidence == "high":
                confidence = "medium"
            confidence_reasons.append("Complete device-level sensors were unavailable for the Ollama host.")
        if any(item["placement"] is None or item["placement"].get("kind") == "unknown" for item in eligible):
            confidence = "low"
            confidence_reasons.append("Processor placement was unavailable for at least one candidate.")
        if objective == "low_energy" and any(
            item["medians"]["tokens_per_joule"] is None for item in eligible
        ):
            confidence = "low"
            confidence_reasons.append(
                "Direct power or derived token-per-joule evidence was missing for at least one candidate."
            )
        failed_count = len([item for item in results if item["state"] in {"failed", "skipped"}])
        if failed_count:
            if confidence == "high":
                confidence = "medium"
            confidence_reasons.append(
                f"{failed_count} candidate(s) failed or were skipped at a safety boundary."
            )
    if not confidence_reasons and confidence != "unavailable":
        confidence_reasons.append("Repeated measurements were consistent and device evidence was complete.")

    deltas = None
    if winner and baseline and baseline["medians"]["generation_tokens_per_second"]:
        base_rate = baseline["medians"]["generation_tokens_per_second"]
        base_ttft = baseline["medians"]["ttft_ms"]
        deltas = {
            "context_tokens": winner["context_length"] - baseline["context_length"],
            "generation_rate_percent": round(
                ((winner["medians"]["generation_tokens_per_second"] - base_rate) / base_rate) * 100, 1
            ),
            "ttft_percent": round(
                ((winner["medians"]["ttft_ms"] - base_ttft) / base_ttft) * 100, 1
            ) if base_ttft and winner["medians"]["ttft_ms"] is not None else None,
            "loaded_size_bytes": (
                winner["loaded_size_bytes"] - baseline["loaded_size_bytes"]
                if winner["loaded_size_bytes"] is not None and baseline["loaded_size_bytes"] is not None
                else None
            ),
        }

    return {
        "score_version": SCORE_VERSION,
        "variance_method": "maximum_within_workload_cv",
        "objective": objective,
        "setting_scope": "model_profile",
        "weights": weights,
        "workload_context_need": workload_context_need,
        "candidate_results": results,
        "pareto_candidate_ids": pareto,
        "baseline_candidate_id": baseline["candidate_id"] if baseline else None,
        "winner_candidate_id": winner["candidate_id"] if winner else None,
        "winning_context_length": winner["context_length"] if winner else None,
        "deltas_from_current": deltas,
        "failed_candidate_ids": [item["candidate_id"] for item in results if item["state"] in {"failed", "skipped"}],
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "keep_current_settings": {
            "candidate_id": baseline["candidate_id"] if baseline else None,
            "context_length": baseline["context_length"] if baseline else None,
            "available": baseline is not None,
        },
        "plain_language": (
            f"For the {objective.replace('_', ' ')} goal, the measured winner is "
            f"{winner['context_length']:,} context tokens for this model profile. "
            "This is a recommendation only; no setting was changed."
            if winner
            else "No context recommendation could be made from the completed measurements. Keep the current setting."
        ),
    }
