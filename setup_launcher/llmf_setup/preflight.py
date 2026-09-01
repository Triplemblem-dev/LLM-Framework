from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import platform
import shutil
import socket
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .command import CommandResult, find_executable, run_command
from .integrity import verify_production_inputs


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    status: str
    detail: str
    action: str


def _command_check(
    key: str,
    label: str,
    args: tuple[str, ...],
    missing_action: str,
    runner: Callable[..., CommandResult],
) -> Check:
    if find_executable(args[0]) is None:
        return Check(key, label, "missing", "Not installed or not on PATH.", missing_action)
    result = runner(args, timeout=15)
    if not result.ok:
        return Check(key, label, "warning", "Installed, but the check did not complete.", missing_action)
    first_line = next((line.strip() for line in result.output.splitlines() if line.strip()), "Available")
    return Check(key, label, "ready", first_line[:240], "No action needed.")


def _port_check(port: int) -> Check:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
        return Check(f"port-{port}", f"Port {port}", "ready", "Available on localhost.", "No action needed.")
    except OSError:
        return Check(
            f"port-{port}",
            f"Port {port}",
            "warning",
            "Already in use. This may be an existing framework installation.",
            f"Stop the other service using port {port}, or verify the existing installation.",
        )
    finally:
        sock.close()


def check_ollama(endpoint: str = "http://127.0.0.1:11434") -> Check:
    url = endpoint.rstrip("/") + "/api/version"
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=3) as response:  # noqa: S310 - validated local/admin endpoint
            if response.status != 200:
                raise HTTPError(url, response.status, "unexpected status", response.headers, None)
            body = response.read(16_384)
        version = json.loads(body.decode("utf-8")).get("version", "version unavailable")
        return Check("ollama-service", "Ollama service", "ready", f"Reachable ({version}).", "No action needed.")
    except (OSError, ValueError, URLError, HTTPError, json.JSONDecodeError):
        return Check(
            "ollama-service",
            "Ollama service",
            "missing",
            "Not reachable on this computer.",
            "Install and start Ollama, or select bundled/remote Ollama.",
        )


def run_preflight(project_root: Path, runner: Callable[..., CommandResult] = run_command) -> list[Check]:
    integrity = verify_production_inputs(project_root)
    checks = [
        Check("platform", "Operating system", "ready", f"{platform.system()} {platform.release()}", "No action needed."),
        Check(
            "integrity",
            "Production files",
            "ready" if integrity.status == "verified" else "warning" if integrity.status == "development" else "missing",
            integrity.detail,
            "No action needed."
            if integrity.status == "verified"
            else "Use a packaged release for verified installation."
            if integrity.status == "development"
            else "Download and extract a fresh matching production bundle.",
        ),
        _command_check("docker-cli", "Docker", ("docker", "--version"), "Install Docker Desktop or Docker Engine.", runner),
        _command_check("compose", "Docker Compose", ("docker", "compose", "version"), "Install the Docker Compose plugin.", runner),
    ]

    if find_executable("docker"):
        daemon = runner(("docker", "info", "--format", "{{.ServerVersion}}"), timeout=15)
        checks.append(
            Check(
                "docker-daemon",
                "Docker service",
                "ready" if daemon.ok else "missing",
                f"Running ({daemon.output.strip()[:100]})." if daemon.ok else "Docker is installed but not running.",
                "No action needed." if daemon.ok else "Start Docker Desktop or the Docker service, then recheck.",
            )
        )

    checks.append(_command_check("ollama-cli", "Ollama application", ("ollama", "--version"), "Install Ollama or choose bundled Ollama.", runner))
    checks.append(check_ollama())

    if find_executable("nvidia-smi"):
        gpu = runner(("nvidia-smi", "--query-gpu=name", "--format=csv,noheader"), timeout=15)
        detail = (
            f"Detected: {gpu.output.strip()[:200]}. Detection does not prove Ollama is using it."
            if gpu.ok
            else "NVIDIA tooling exists, but accelerator availability could not be verified."
        )
        checks.append(
            Check(
                "gpu",
                "Accelerator",
                "warning",
                detail,
                "Complete setup, load a model, then use Model Performance Optimizer to observe actual placement.",
            )
        )
    elif platform.system() == "Darwin" and platform.machine().lower() == "arm64":
        checks.append(
            Check(
                "gpu",
                "Accelerator",
                "warning",
                "Apple unified-memory accelerator detected; native Ollama can use Metal. Detection does not prove current placement.",
                "Choose native Ollama, then use Model Performance Optimizer to observe actual placement.",
            )
        )
    else:
        checks.append(
            Check(
                "gpu",
                "Accelerator",
                "warning",
                "No supported accelerator was detected by the launcher. This is not proof that none is available.",
                "CPU operation remains available; verify placement after setup in Model Performance Optimizer.",
            )
        )

    try:
        free = shutil.disk_usage(project_root).free
        gib = free / (1024**3)
        status = "ready" if gib >= 20 else "warning" if gib >= 10 else "missing"
        detail = f"{gib:.1f} GiB free; 20 GiB or more is recommended."
        action = "No action needed." if status == "ready" else "Free disk space before downloading images and models."
        checks.append(Check("disk", "Disk space", status, detail, action))
    except OSError as exc:
        checks.append(Check("disk", "Disk space", "warning", f"Could not inspect disk: {exc}", "Check free space manually."))

    checks.extend((_port_check(3000), _port_check(8000)))
    env_path = project_root / ".env"
    checks.append(
        Check(
            "configuration",
            "Configuration",
            "warning" if env_path.exists() else "ready",
            "Existing .env detected; it will be preserved by default." if env_path.exists() else "No existing installation configuration.",
            "Review before replacing." if env_path.exists() else "The launcher will create it during setup.",
        )
    )
    return checks
