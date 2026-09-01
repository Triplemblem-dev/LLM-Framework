from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .command import CommandResult, find_executable, run_command
from .config import (
    ConfigWriteResult,
    SetupOptions,
    existing_ollama_mode,
    normalized_options,
    read_env_value,
    validate_model_tag,
    write_configuration,
)
from .integrity import require_production_integrity


StageCallback = Callable[[str, str], None]


@dataclass(frozen=True)
class SetupResult:
    configuration: ConfigWriteResult
    frontend_url: str
    backend_url: str


class SetupFailure(RuntimeError):
    def __init__(self, stage: str, message: str, action: str):
        super().__init__(message)
        self.stage = stage
        self.action = action


def _require(result: CommandResult, stage: str, message: str, action: str) -> None:
    if result.ok:
        return
    suffix = " The operation timed out." if result.timed_out else ""
    raise SetupFailure(stage, message + suffix, action)


def _compose(root: Path, args: tuple[str, ...], timeout: int = 900) -> CommandResult:
    return run_command(("docker", "compose", *args), cwd=root, timeout=timeout)


def test_ollama_endpoint(endpoint: str, timeout: int = 5) -> bool:
    request = Request(endpoint.rstrip("/") + "/api/version", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-provided model endpoint
            body = response.read(16_384)
            return response.status == 200 and isinstance(json.loads(body.decode("utf-8")), dict)
    except (OSError, ValueError, URLError, HTTPError, json.JSONDecodeError):
        return False


def _wait_for_http(url: str, timeout: int, *, expect_json: bool = False) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=3) as response:  # noqa: S310
                body = response.read(65_536)
                if response.status == 200:
                    if expect_json:
                        json.loads(body.decode("utf-8"))
                    return True
        except (OSError, ValueError, URLError, HTTPError, json.JSONDecodeError):
            pass
        time.sleep(2)
    return False


def _activate_model(model: str, access_token: str) -> bool:
    payload = json.dumps({"ollama_tag": model}).encode("utf-8")
    request = Request(
        "http://127.0.0.1:8000/models/profile",
        data=payload,
        method="PUT",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed local framework endpoint
            body = json.loads(response.read(65_536).decode("utf-8"))
            return response.status == 200 and body.get("tag") == model
    except (OSError, ValueError, URLError, HTTPError, json.JSONDecodeError):
        return False


def _pull_native(model: str, root: Path) -> CommandResult:
    return run_command(("ollama", "pull", model), cwd=root, timeout=1800)


def _pull_bundled(model: str, root: Path) -> CommandResult:
    return _compose(root, ("exec", "-T", "ollama", "ollama", "pull", model), timeout=1800)


def _verify_ollama_from_backend(root: Path) -> CommandResult:
    script = (
        "import json,os,urllib.request;"
        "u=os.environ['OLLAMA_HOST'].rstrip('/')+'/api/version';"
        "r=urllib.request.urlopen(u,timeout=10);"
        "d=json.loads(r.read(16384));"
        "assert r.status==200 and isinstance(d.get('version'),str)"
    )
    return _compose(root, ("exec", "-T", "backend", "python", "-c", script), timeout=30)


def perform_setup(options: SetupOptions, callback: StageCallback) -> SetupResult:
    try:
        clean = normalized_options(options)
    except (OSError, ValueError) as exc:
        raise SetupFailure(
            "validation",
            str(exc),
            "Correct the repository folder, endpoint, and model fields, then retry.",
        ) from exc
    root = clean.project_root
    try:
        require_production_integrity(root)
    except ValueError as exc:
        raise SetupFailure(
            "integrity",
            str(exc),
            "Download and extract a fresh production bundle that matches this launcher.",
        ) from exc
    env_path = root / ".env"
    if env_path.exists() and not clean.replace_existing:
        try:
            existing_mode, existing_endpoint = existing_ollama_mode(env_path)
            existing_embedding = validate_model_tag(
                read_env_value(env_path, "EMBEDDING_MODEL") or clean.embedding_model,
                "Existing embedding model",
            )
        except (OSError, ValueError) as exc:
            raise SetupFailure(
                "configuration",
                f"Existing configuration is invalid: {exc}",
                "Preview and repair the existing .env manually, or explicitly replace it after confirming a backup.",
            ) from exc
        clean = replace(
            clean,
            ollama_mode=existing_mode,
            ollama_endpoint=existing_endpoint,
            embedding_model=existing_embedding,
        )
        callback("configuration", f"Existing configuration selects {existing_mode} Ollama; setup controls will not override it.")

    callback("preflight", "Checking Docker and the selected Ollama configuration.")
    if find_executable("docker") is None:
        raise SetupFailure("preflight", "Docker is not installed.", "Use Install Docker, start it, and run the check again.")
    _require(
        run_command(("docker", "info", "--format", "{{.ServerVersion}}"), timeout=20),
        "preflight",
        "Docker is installed but its service is not ready.",
        "Start Docker Desktop or the Docker service, wait until it is ready, and retry.",
    )
    _require(
        run_command(("docker", "compose", "version"), timeout=20),
        "preflight",
        "Docker Compose is unavailable.",
        "Install the Docker Compose plugin and retry.",
    )

    if clean.ollama_mode == "native":
        if find_executable("ollama") is None or not test_ollama_endpoint("http://127.0.0.1:11434"):
            raise SetupFailure(
                "preflight",
                "Native Ollama is not installed and running.",
                "Install and start Ollama, then retry; or choose bundled Ollama.",
            )
    elif clean.ollama_mode == "remote" and not test_ollama_endpoint(clean.ollama_endpoint):
        raise SetupFailure(
            "preflight",
            "The remote Ollama endpoint did not answer its version API.",
            "Check the URL, TLS/network access, and remote Ollama service before retrying.",
        )

    callback("configuration", "Creating or preserving the local configuration.")
    try:
        configuration = write_configuration(clean)
    except (OSError, ValueError) as exc:
        raise SetupFailure(
            "configuration",
            f"Configuration could not be written safely: {exc}",
            "Check folder permissions and the redacted existing configuration, then retry.",
        ) from exc
    if configuration.backup_path:
        callback("configuration", f"Previous configuration backed up as {configuration.backup_path.name}.")
    elif not configuration.created:
        callback("configuration", "Existing configuration preserved.")

    infrastructure = ("up", "-d", "postgres", "ollama") if clean.ollama_mode == "bundled" else ("up", "-d", "postgres")
    callback("infrastructure", "Starting PostgreSQL" + (" and bundled Ollama." if clean.ollama_mode == "bundled" else "."))
    _require(
        _compose(root, infrastructure),
        "infrastructure",
        "The required infrastructure did not start.",
        "Open Docker, check available disk space, then retry. Existing downloaded layers are preserved.",
    )

    callback("models", f"Pulling chat model {clean.chat_model}.")
    if clean.ollama_mode != "remote":
        pull = _pull_bundled if clean.ollama_mode == "bundled" else _pull_native
        _require(
            pull(clean.chat_model, root),
            "models",
            f"Could not pull chat model {clean.chat_model}.",
            "Check the model tag, network connection, Ollama logs, and free disk space, then retry.",
        )
        callback("models", f"Pulling embedding model {clean.embedding_model}.")
        _require(
            pull(clean.embedding_model, root),
            "models",
            f"Could not pull embedding model {clean.embedding_model}.",
            "Check the model tag, network connection, Ollama logs, and free disk space, then retry.",
        )
    else:
        callback("models", "Remote mode does not install models; verifying the endpoint again.")
        if not test_ollama_endpoint(clean.ollama_endpoint):
            raise SetupFailure("models", "Remote Ollama became unreachable.", "Restore the endpoint and retry.")

    callback("application", "Building and starting the backend and frontend.")
    _require(
        _compose(root, ("up", "-d", "--build", "backend", "frontend"), timeout=1800),
        "application",
        "The application containers did not build and start.",
        "Review Docker's available storage and the container logs, then retry.",
    )

    callback("health", "Waiting for backend and frontend health checks.")
    if not _wait_for_http("http://127.0.0.1:8000/health", 120, expect_json=True):
        raise SetupFailure(
            "health",
            "The backend did not become healthy.",
            "Run 'docker compose logs backend postgres' from the project folder and review the first error.",
        )
    _require(
        _verify_ollama_from_backend(root),
        "health",
        "The backend started but cannot reach its configured Ollama endpoint.",
        "Check OLLAMA_HOST, container-to-host networking, and the Ollama service, then retry.",
    )
    callback("model-profile", f"Selecting {clean.chat_model} as the active framework model.")
    if not _activate_model(clean.chat_model, configuration.access_token):
        raise SetupFailure(
            "model-profile",
            f"The backend could not activate {clean.chat_model}.",
            "Confirm that the model exists at the configured Ollama endpoint, then retry setup.",
        )
    if not _wait_for_http("http://127.0.0.1:3000", 120):
        raise SetupFailure(
            "health",
            "The frontend did not become reachable.",
            "Run 'docker compose logs frontend' from the project folder and review the first error.",
        )

    callback("complete", "Installation verified successfully.")
    return SetupResult(configuration, "http://localhost:3000", "http://localhost:8000")
