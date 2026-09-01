"""Redacted, local-only Markdown export for optimizer reports."""

from app.models import OptimizationRun


def _value(value) -> str:
    return "Unavailable" if value is None else str(value)


def redacted_markdown(run: OptimizationRun) -> str:
    summary = run.summary or {}
    recommendation = summary.get("recommendation") or {}
    hardware = run.hardware_snapshot or {}
    ollama = hardware.get("ollama") or {}
    selected = hardware.get("selected_model") or {}
    lines = [
        "# Model Performance Optimizer — Redacted Report",
        "",
        f"- Captured: {run.completed_at or run.created_at}",
        f"- State: {run.state}",
        f"- Model parameters: {_value(selected.get('parameter_size'))}",
        f"- Objective: {run.objective}",
        f"- Workload: {run.workload_version}",
        f"- Runner: {run.runner_version}",
        f"- Ollama version: {_value(run.ollama_version)}",
        f"- Ollama relationship: {_value(ollama.get('relationship'))}",
        f"- Model quantization: {_value(selected.get('quantization_level'))}",
        "- Generated text retained: no",
        "- Persistent settings changed: no",
        "",
        "## Candidate measurements",
        "",
        "| Context | State | Trials | TTFT (ms) | Generation (tok/s) | Power (W) | Efficiency (tok/J) | Loaded bytes | Placement | Score |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for item in recommendation.get("candidate_results", []):
        medians = item.get("medians") or {}
        placement = item.get("placement") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("context_length", "?")),
                    str(item.get("state", "unknown")),
                    str(item.get("measured_trials", 0)),
                    _value(medians.get("ttft_ms")),
                    _value(medians.get("generation_tokens_per_second")),
                    _value(medians.get("power_watts")),
                    _value(medians.get("tokens_per_joule")),
                    _value(item.get("loaded_size_bytes")),
                    str(placement.get("kind", "unknown")),
                    _value(item.get("score")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            recommendation.get("plain_language") or "No recommendation is available.",
            "",
            "Scope: per-model profile (not a server-global Ollama setting)",
            "",
            f"Confidence: **{recommendation.get('confidence', 'unavailable')}**",
            "",
            "Reasons:",
            *[f"- {reason}" for reason in recommendation.get("confidence_reasons", [])],
            "",
            f"Scoring rule: `{recommendation.get('score_version', 'unavailable')}`",
            f"Recommendation evaluated: {_value(summary.get('recommendation_evaluated_at'))}",
            f"Visible weights: `{recommendation.get('weights', {})}`",
            "Energy efficiency is an estimate from the observed accelerator power snapshot and trial wall duration; it is omitted when direct power is unavailable.",
            "",
            "The configured endpoint address, hostnames, paths, usernames, credentials, machine IDs, serial numbers, prompts, and generated answers are intentionally omitted.",
        ]
    )
    return "\n".join(lines) + "\n"
