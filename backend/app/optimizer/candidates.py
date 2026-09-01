"""Pure, bounded context-candidate planning for optimizer comparisons."""

from dataclasses import dataclass

from app.optimizer.workloads import MAX_CANDIDATES, WORKLOAD_CONTEXT_NEED


MIN_CONTEXT = 512


@dataclass(frozen=True)
class ContextCandidatePlan:
    context_length: int
    is_current: bool
    label: str


def _rounded_512(value: float) -> int:
    return max(MIN_CONTEXT, int(value // 512) * 512)


def context_candidates(
    current_context: int,
    native_context_limit: int | None,
    safety_ceiling: int,
) -> list[ContextCandidatePlan]:
    """Return 1-4 unique candidates, conservatively ordered from small to large."""
    if safety_ceiling < MIN_CONTEXT:
        raise ValueError("Optimizer context ceiling must be at least 512 tokens")
    reported_limit = native_context_limit if native_context_limit and native_context_limit > 0 else safety_ceiling
    safe_limit = max(MIN_CONTEXT, min(reported_limit, safety_ceiling))
    current = max(MIN_CONTEXT, min(current_context, safe_limit))

    values = {
        current,
        *(value for value in (WORKLOAD_CONTEXT_NEED, 8_192, 16_384, 32_768, 65_536) if value <= safe_limit),
    }
    if len(values) < 3 and safe_limit >= MIN_CONTEXT * 3:
        values.update({_rounded_512(safe_limit / 3), _rounded_512(safe_limit * 2 / 3), safe_limit})
    values = {max(MIN_CONTEXT, min(value, safe_limit)) for value in values}

    ordered = sorted(values)
    if len(ordered) > MAX_CANDIDATES:
        anchors = {ordered[0], current, ordered[-1]}
        remaining = [value for value in ordered if value not in anchors]
        if remaining and len(anchors) < MAX_CANDIDATES:
            target = (ordered[0] + ordered[-1]) / 2
            anchors.add(min(remaining, key=lambda value: abs(value - target)))
        ordered = sorted(anchors)[:MAX_CANDIDATES]

    return [
        ContextCandidatePlan(
            context_length=value,
            is_current=value == current,
            label=f"{value:,} context" + (" · current" if value == current else ""),
        )
        for value in ordered
    ]
