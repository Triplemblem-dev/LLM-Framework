"""Versioned, built-in benchmark inputs containing no user or framework data."""

from dataclasses import dataclass


WORKLOAD_VERSION = "baseline-v1"
CONTEXT_WORKLOAD_VERSION = "context-comparison-v1"
MAX_PROMPT_CHARACTERS = 12_000
MAX_RESPONSE_TOKENS = 128
MAX_TRIALS_PER_CANDIDATE = 10
MAX_CANDIDATES = 4
MAX_RUN_SECONDS = 1_800
WORKLOAD_CONTEXT_NEED = 4_096


@dataclass(frozen=True)
class WorkloadCase:
    key: str
    prompt: str


PROMPT_BANK = (
    WorkloadCase(
        key="short_response",
        prompt=(
            "This is a synthetic performance test. In exactly four short bullet points, "
            "explain how to keep a desk organized. Do not mention this test."
        ),
    ),
    WorkloadCase(
        key="sustained_generation",
        prompt=(
            "This is a synthetic performance test. Write a compact, practical guide to "
            "planning a weekly study routine. Use headings and concrete steps. Do not "
            "mention this test or request external information."
        ),
    ),
    WorkloadCase(
        key="controlled_context",
        prompt=(
            "This is a synthetic context test. The following identifiers are fictional: "
            + " ".join(f"ITEM-{index:03d}" for index in range(1, 161))
            + ". Return only the identifiers numbered 017, 063, 104, and 149 in that order."
        ),
    ),
)


def measured_repetitions(mode: str, benchmark_kind: str = "baseline") -> int:
    if benchmark_kind == "context_comparison":
        return 2 if mode == "quick" else 3
    return 0


def measured_trial_count(mode: str, benchmark_kind: str = "baseline") -> int:
    if benchmark_kind == "context_comparison":
        return len(PROMPT_BANK) * measured_repetitions(mode, benchmark_kind)
    return 2 if mode == "quick" else 3


def trial_plan(mode: str, benchmark_kind: str = "baseline") -> list[tuple[bool, WorkloadCase]]:
    """Warm once, then repeat like-for-like workloads when confidence is scored."""
    plan = [(True, PROMPT_BANK[0])]
    if benchmark_kind == "context_comparison":
        for workload in PROMPT_BANK:
            plan.extend(
                (False, workload)
                for _repetition in range(measured_repetitions(mode, benchmark_kind))
            )
        return plan
    measured = measured_trial_count(mode, benchmark_kind)
    plan.extend((False, PROMPT_BANK[(index + 1) % len(PROMPT_BANK)]) for index in range(measured))
    return plan
