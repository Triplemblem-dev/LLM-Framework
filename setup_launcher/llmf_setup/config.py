from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import secrets
import shutil
import tempfile
from urllib.parse import urlsplit


MODEL_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}(?::[A-Za-z0-9][A-Za-z0-9._-]{0,79})?$")


@dataclass(frozen=True)
class SetupOptions:
    project_root: Path
    ollama_mode: str
    ollama_endpoint: str
    chat_model: str
    embedding_model: str
    replace_existing: bool = False


@dataclass(frozen=True)
class ConfigWriteResult:
    path: Path
    access_token: str
    backup_path: Path | None
    created: bool


def validate_project_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    required = ("docker-compose.yml", "backend", "frontend")
    missing = [name for name in required if not (resolved / name).exists()]
    if missing:
        raise ValueError(f"Selected folder is not an LLM Framework checkout (missing: {', '.join(missing)})")
    return resolved


def validate_model_tag(value: str, label: str) -> str:
    clean = value.strip()
    if not MODEL_TAG.fullmatch(clean):
        raise ValueError(f"{label} is not a valid model tag")
    return clean


def validate_endpoint(value: str) -> str:
    clean = value.strip().rstrip("/")
    try:
        parsed = urlsplit(clean)
    except ValueError as exc:
        raise ValueError("Ollama endpoint is not a valid URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Ollama endpoint must be an http:// or https:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Ollama endpoint cannot contain credentials, a query, or a fragment")
    return clean


def normalized_options(options: SetupOptions) -> SetupOptions:
    if options.ollama_mode not in {"native", "bundled", "remote"}:
        raise ValueError("Unknown Ollama mode")
    endpoint = validate_endpoint(options.ollama_endpoint)
    if options.ollama_mode == "bundled" and endpoint != "http://ollama:11434":
        raise ValueError("Bundled Ollama must use its internal service endpoint")
    if options.ollama_mode == "native" and endpoint != "http://host.docker.internal:11434":
        raise ValueError("Native Ollama must use the host gateway endpoint")
    return SetupOptions(
        project_root=validate_project_root(options.project_root),
        ollama_mode=options.ollama_mode,
        ollama_endpoint=endpoint,
        chat_model=validate_model_tag(options.chat_model, "Chat model"),
        embedding_model=validate_model_tag(options.embedding_model, "Embedding model"),
        replace_existing=options.replace_existing,
    )


def _secret() -> str:
    return secrets.token_hex(32)


def render_env(*, postgres_password: str, access_token: str, endpoint: str, embedding_model: str) -> str:
    values = (postgres_password, access_token)
    if any(not value or "\n" in value or "\r" in value for value in values):
        raise ValueError("Generated secret is invalid")
    endpoint = validate_endpoint(endpoint)
    embedding_model = validate_model_tag(embedding_model, "Embedding model")
    return (
        "# Generated locally by LLM Framework Setup. Do not commit this file.\n"
        "POSTGRES_USER=llmframework\n"
        f"POSTGRES_PASSWORD={postgres_password}\n"
        "POSTGRES_DB=llmframework\n"
        f"APP_ACCESS_TOKEN={access_token}\n"
        "NEXT_PUBLIC_API_URL=http://localhost:8000\n"
        "CORS_ORIGINS=http://localhost:3000\n"
        f"OLLAMA_HOST={endpoint}\n"
        f"EMBEDDING_MODEL={embedding_model}\n"
    )


def write_configuration(options: SetupOptions) -> ConfigWriteResult:
    clean = normalized_options(options)
    env_path = clean.project_root / ".env"
    if env_path.exists() and not clean.replace_existing:
        token = read_access_token(env_path)
        if not token:
            raise FileExistsError("Existing .env has no readable APP_ACCESS_TOKEN; review it before continuing")
        return ConfigWriteResult(env_path, token, None, created=False)

    backup_path = None
    if env_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = clean.project_root / f".env.backup-{stamp}"
        suffix = 1
        while backup_path.exists():
            backup_path = clean.project_root / f".env.backup-{stamp}-{suffix}"
            suffix += 1
        backup_fd, backup_temp_name = tempfile.mkstemp(prefix=".env.backup-tmp-", dir=clean.project_root)
        os.close(backup_fd)
        backup_temp = Path(backup_temp_name)
        try:
            shutil.copy2(env_path, backup_temp)
            with backup_temp.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(backup_temp, backup_path)
        except BaseException:
            backup_temp.unlink(missing_ok=True)
            raise
        try:
            os.chmod(backup_path, 0o600)
        except OSError:
            pass

    access_token = _secret()
    content = render_env(
        postgres_password=_secret(),
        access_token=access_token,
        endpoint=clean.ollama_endpoint,
        embedding_model=clean.embedding_model,
    )
    fd, temporary_name = tempfile.mkstemp(prefix=".env.tmp-", dir=clean.project_root, text=True)
    temporary_path = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, env_path)
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return ConfigWriteResult(env_path, access_token, backup_path, created=True)


def read_access_token(path: Path) -> str | None:
    return read_env_value(path, "APP_ACCESS_TOKEN")


def read_env_value(path: Path, key: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith(f"{key}="):
            value = line.partition("=")[2].strip()
            return value or None
    return None


def existing_ollama_mode(path: Path) -> tuple[str, str]:
    endpoint = validate_endpoint(read_env_value(path, "OLLAMA_HOST") or "http://ollama:11434")
    if endpoint == "http://ollama:11434":
        return "bundled", endpoint
    if endpoint == "http://host.docker.internal:11434":
        return "native", endpoint
    return "remote", endpoint


def redacted_env_preview(path: Path) -> str:
    if not path.exists():
        return "No existing .env configuration."
    result: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key = line.partition("=")[0].strip().upper()
        if key in {"POSTGRES_PASSWORD", "APP_ACCESS_TOKEN"} and "=" in line:
            result.append(f"{line.partition('=')[0]}=<redacted>")
        else:
            result.append(line)
    return "\n".join(result)
