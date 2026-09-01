"""In-process Ollama workload coordination.

The production Compose deployment runs one backend worker. The durable database
lock in the optimizer router coordinates benchmark jobs across processes; this
small registry additionally prevents known chat and embedding work in this
process from overlapping a benchmark.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import threading
import uuid


class OllamaBusyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActivitySnapshot:
    chats: int
    embeddings: int
    benchmark_run_id: str | None

    @property
    def ordinary_workloads(self) -> int:
        return self.chats + self.embeddings


_lock = threading.RLock()
_counts = {"chat": 0, "embedding": 0}
_benchmark_run_id: str | None = None


def snapshot() -> ActivitySnapshot:
    with _lock:
        return ActivitySnapshot(
            chats=_counts["chat"],
            embeddings=_counts["embedding"],
            benchmark_run_id=_benchmark_run_id,
        )


@contextmanager
def ordinary_activity(kind: str):
    if kind not in _counts:
        raise ValueError(f"Unknown Ollama activity kind: {kind}")
    with _lock:
        if _benchmark_run_id is not None:
            raise OllamaBusyError(
                "A Model Performance Optimizer benchmark is using Ollama. "
                "Wait for it to finish or cancel it before retrying."
            )
        _counts[kind] += 1
    try:
        yield
    finally:
        with _lock:
            _counts[kind] = max(0, _counts[kind] - 1)


def try_acquire_benchmark(run_id: uuid.UUID | str) -> bool:
    global _benchmark_run_id
    value = str(run_id)
    with _lock:
        if _benchmark_run_id not in {None, value} or sum(_counts.values()) > 0:
            return False
        _benchmark_run_id = value
        return True


def release_benchmark(run_id: uuid.UUID | str) -> None:
    global _benchmark_run_id
    with _lock:
        if _benchmark_run_id == str(run_id):
            _benchmark_run_id = None
