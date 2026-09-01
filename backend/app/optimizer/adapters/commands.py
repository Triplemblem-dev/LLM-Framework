"""Fixed, read-only platform commands.

No route, request field, or model output can select a binary, argument, working
directory, or environment value. Callers receive bounded output only.
"""

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class CommandSpec:
    paths: tuple[str, ...]
    arguments: tuple[str, ...]
    timeout_seconds: float = 5.0


COMMANDS: dict[str, CommandSpec] = {
    "mac_cpu_brand": CommandSpec(("/usr/sbin/sysctl",), ("-n", "machdep.cpu.brand_string")),
    "mac_physical_cores": CommandSpec(("/usr/sbin/sysctl",), ("-n", "hw.physicalcpu")),
    "mac_logical_cores": CommandSpec(("/usr/sbin/sysctl",), ("-n", "hw.logicalcpu")),
    "mac_total_memory": CommandSpec(("/usr/sbin/sysctl",), ("-n", "hw.memsize")),
    "mac_swap": CommandSpec(("/usr/sbin/sysctl",), ("-n", "vm.swapusage")),
    "mac_vm_stat": CommandSpec(("/usr/bin/vm_stat",), ()),
    "mac_displays": CommandSpec(
        ("/usr/sbin/system_profiler",), ("SPDisplaysDataType", "-json"), timeout_seconds=8.0
    ),
    "linux_nvidia": CommandSpec(
        ("/usr/bin/nvidia-smi", "/usr/local/bin/nvidia-smi"),
        (
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,power.draw,temperature.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ),
    ),
}


def run_allowed(key: str) -> str | None:
    spec = COMMANDS.get(key)
    if spec is None:
        raise ValueError(f"Unknown fixed command: {key}")

    executable = next((path for path in spec.paths if Path(path).is_file()), None)
    if executable is None:
        return None

    try:
        completed = subprocess.run(
            [executable, *spec.arguments],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=spec.timeout_seconds,
            env={
                "LC_ALL": "C",
                "LANG": "C",
                "PATH": "/usr/bin:/usr/sbin:/bin:/sbin",
            },
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout[:1_000_000]
