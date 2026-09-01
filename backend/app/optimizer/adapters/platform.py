from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
from typing import Any

from app.optimizer.adapters.commands import run_allowed
from app.optimizer.schemas import (
    AcceleratorSnapshot,
    CpuSnapshot,
    MemorySnapshot,
    RuntimeHostSnapshot,
    StorageSnapshot,
)

MIB = 1024 * 1024


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"n/a", "[not supported]", "not supported"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _read_bounded(path: str, limit: int = 1_000_000) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return None


def _is_container() -> bool:
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return True
    cgroup = _read_bounded("/proc/1/cgroup", 100_000) or ""
    markers = ("docker", "containerd", "kubepods", "lxc", "podman")
    return any(marker in cgroup.lower() for marker in markers)


def parse_linux_meminfo(text: str) -> MemorySnapshot:
    values: dict[str, int] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([^:]+):\s+(\d+)\s+kB", line.strip())
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    return MemorySnapshot(
        total_bytes=values.get("MemTotal"),
        available_bytes=values.get("MemAvailable"),
        swap_total_bytes=swap_total,
        swap_used_bytes=(max(0, swap_total - swap_free) if swap_total is not None and swap_free is not None else None),
    )


def parse_linux_cpuinfo(text: str) -> tuple[str | None, int | None]:
    model = None
    physical_pairs: set[tuple[str, str]] = set()
    current: dict[str, str] = {}
    for line in [*text.splitlines(), ""]:
        if not line.strip():
            if current.get("physical id") is not None and current.get("core id") is not None:
                physical_pairs.add((current["physical id"], current["core id"]))
            current = {}
            continue
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        current[key] = value
        if model is None and key in {"model name", "Processor", "Hardware"}:
            model = value
    return model, len(physical_pairs) or None


def parse_nvidia_smi(text: str) -> list[AcceleratorSnapshot]:
    accelerators: list[AcceleratorSnapshot] = []
    for line in text.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 7 or not fields[0]:
            continue
        memory_total = _float_or_none(fields[1])
        memory_used = _float_or_none(fields[2])
        accelerators.append(
            AcceleratorSnapshot(
                vendor="nvidia",
                name=fields[0][:200],
                compute_backend="CUDA",
                memory_kind="dedicated",
                memory_total_bytes=round(memory_total * MIB) if memory_total is not None else None,
                memory_used_bytes=round(memory_used * MIB) if memory_used is not None else None,
                utilization_percent=_float_or_none(fields[3]),
                power_watts=_float_or_none(fields[4]),
                temperature_celsius=_float_or_none(fields[5]),
                driver_version=fields[6][:100] or None,
                source="nvidia-smi fixed query",
            )
        )
    return accelerators


def parse_vm_stat(text: str) -> tuple[int | None, int | None]:
    page_match = re.search(r"page size of (\d+) bytes", text)
    if page_match is None:
        return None, None
    page_size = int(page_match.group(1))
    pages: dict[str, int] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"Pages ([^:]+):\s+(\d+)\.", line.strip())
        if match:
            pages[match.group(1)] = int(match.group(2))
    available_names = ("free", "inactive", "speculative", "purgeable")
    available_pages = sum(pages.get(name, 0) for name in available_names)
    used_names = ("active", "wired down", "occupied by compressor")
    used_pages = sum(pages.get(name, 0) for name in used_names)
    return available_pages * page_size, used_pages * page_size


def parse_macos_swap(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    total = re.search(r"total\s*=\s*([0-9.]+)([MG])", text)
    used = re.search(r"used\s*=\s*([0-9.]+)([MG])", text)

    def convert(match: re.Match[str] | None) -> int | None:
        if match is None:
            return None
        multiplier = MIB if match.group(2) == "M" else 1024 * MIB
        return round(float(match.group(1)) * multiplier)

    return convert(total), convert(used)


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def parse_macos_displays(text: str, total_memory: int | None) -> list[AcceleratorSnapshot]:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []

    accelerators: list[AcceleratorSnapshot] = []
    seen: set[str] = set()
    for item in _walk_dicts(payload):
        name = item.get("sppci_model") or item.get("chipset_model") or item.get("_name")
        metal = item.get("spdisplays_metal") or item.get("metal")
        if not isinstance(name, str) or ("display" in name.lower() and not metal):
            continue
        if not metal and "apple" not in name.lower() and "gpu" not in name.lower():
            continue
        clean_name = name[:200]
        if clean_name in seen:
            continue
        seen.add(clean_name)
        apple = "apple" in clean_name.lower() or platform.machine().lower() == "arm64"
        accelerators.append(
            AcceleratorSnapshot(
                vendor="apple" if apple else "unknown",
                name=clean_name,
                compute_backend="Metal" if metal or apple else None,
                memory_kind="unified" if apple else "unknown",
                memory_total_bytes=total_memory if apple else None,
                source="system_profiler allow-listed display fields",
            )
        )
    return accelerators


def _storage_snapshot() -> StorageSnapshot:
    try:
        usage = shutil.disk_usage("/")
        return StorageSnapshot(observed_path="runtime root filesystem", total_bytes=usage.total, available_bytes=usage.free)
    except OSError:
        return StorageSnapshot(observed_path="runtime root filesystem")


def _inspect_linux(runtime_kind: str) -> RuntimeHostSnapshot:
    mem_text = _read_bounded("/proc/meminfo") or ""
    cpu_text = _read_bounded("/proc/cpuinfo") or ""
    cpu_model, physical_cores = parse_linux_cpuinfo(cpu_text)
    nvidia_output = run_allowed("linux_nvidia")
    accelerators = parse_nvidia_smi(nvidia_output) if nvidia_output else []
    return RuntimeHostSnapshot(
        runtime_kind=runtime_kind,
        applies_to_ollama_device="unknown",
        os_name=platform.system() or "Linux",
        os_release=platform.release(),
        cpu=CpuSnapshot(
            model=cpu_model,
            architecture=platform.machine(),
            logical_cores=os.cpu_count(),
            physical_cores=physical_cores,
        ),
        memory=parse_linux_meminfo(mem_text),
        storage=_storage_snapshot(),
        accelerators=accelerators,
    )


def _inspect_macos(runtime_kind: str) -> RuntimeHostSnapshot:
    total_memory = _int_or_none(run_allowed("mac_total_memory"))
    available_memory, _used_memory = parse_vm_stat(run_allowed("mac_vm_stat") or "")
    swap_total, swap_used = parse_macos_swap(run_allowed("mac_swap"))
    displays = run_allowed("mac_displays")
    return RuntimeHostSnapshot(
        runtime_kind=runtime_kind,
        applies_to_ollama_device="unknown",
        os_name="macOS",
        os_release=platform.mac_ver()[0] or platform.release(),
        cpu=CpuSnapshot(
            model=(run_allowed("mac_cpu_brand") or "").strip() or None,
            architecture=platform.machine(),
            logical_cores=_int_or_none(run_allowed("mac_logical_cores")) or os.cpu_count(),
            physical_cores=_int_or_none(run_allowed("mac_physical_cores")),
        ),
        memory=MemorySnapshot(
            total_bytes=total_memory,
            available_bytes=available_memory,
            swap_total_bytes=swap_total,
            swap_used_bytes=swap_used,
        ),
        storage=_storage_snapshot(),
        accelerators=parse_macos_displays(displays, total_memory) if displays else [],
    )


def inspect_runtime_host() -> RuntimeHostSnapshot:
    runtime_kind = "container" if _is_container() else "native"
    system = platform.system()
    if system == "Linux":
        return _inspect_linux(runtime_kind)
    if system == "Darwin":
        return _inspect_macos(runtime_kind)

    return RuntimeHostSnapshot(
        runtime_kind=runtime_kind,
        applies_to_ollama_device="unknown",
        os_name=system or "Unknown",
        os_release=platform.release(),
        cpu=CpuSnapshot(architecture=platform.machine(), logical_cores=os.cpu_count()),
        memory=MemorySnapshot(),
        storage=_storage_snapshot(),
        accelerators=[],
    )
