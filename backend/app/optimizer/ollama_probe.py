from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.optimizer.schemas import (
    DiscoveryError,
    OllamaEndpointSnapshot,
    SelectedModelSnapshot,
)


@dataclass
class ProbeResult:
    endpoint: OllamaEndpointSnapshot
    selected_model: SelectedModelSnapshot | None
    requested_model_installed: bool | None


def safe_endpoint_display(configured_endpoint: str) -> str:
    try:
        parsed = urlsplit(configured_endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "Invalid configured Ollama endpoint"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit((parsed.scheme, f"{host}{port}", "", "", ""))
    except ValueError:
        return "Invalid configured Ollama endpoint"


def classify_endpoint(configured_endpoint: str, runtime_kind: str) -> str:
    try:
        host = (urlsplit(configured_endpoint).hostname or "").lower().rstrip(".")
    except ValueError:
        return "unknown"
    if not host:
        return "unknown"
    if host == "localhost" or host == "::1" or host.startswith("127."):
        return "same_runtime"
    if host in {"host.docker.internal", "host.containers.internal", "gateway.docker.internal"}:
        return "native_host"
    if runtime_kind == "container" and host == "ollama":
        return "container_service"
    return "remote"


def _discovery_error(exc: Exception) -> DiscoveryError:
    if isinstance(exc, httpx.TimeoutException):
        return DiscoveryError(
            code="ollama_timeout",
            message="Ollama did not answer before the read-only discovery timeout.",
            action="Check that Ollama is running and that OLLAMA_HOST points to a reachable endpoint.",
        )
    if isinstance(exc, httpx.ConnectError):
        return DiscoveryError(
            code="ollama_unreachable",
            message="The framework could not connect to the configured Ollama endpoint.",
            action="Start Ollama, then verify OLLAMA_HOST and the container/network route.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return DiscoveryError(
            code="ollama_http_error",
            message=f"The configured endpoint returned HTTP {exc.response.status_code} instead of Ollama model data.",
            action="Verify the endpoint, reverse proxy, and Ollama API access.",
        )
    if isinstance(exc, (httpx.InvalidURL, ValueError)):
        return DiscoveryError(
            code="ollama_invalid_endpoint",
            message="OLLAMA_HOST is not a valid HTTP or HTTPS endpoint.",
            action="Set OLLAMA_HOST to an address such as http://localhost:11434.",
        )
    return DiscoveryError(
        code="ollama_invalid_response",
        message="The endpoint answered, but its response could not be read as Ollama model data.",
        action="Check the Ollama version and any proxy in front of its API.",
    )


def _validate_base_url(configured_endpoint: str) -> str:
    parsed = urlsplit(configured_endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid Ollama URL")
    return configured_endpoint.rstrip("/")


def _get_json(client: httpx.Client, path: str) -> dict[str, Any]:
    response = client.get(path)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("expected object")
    return payload


def _post_json(client: httpx.Client, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=body)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("expected object")
    return payload


def _native_context_length(show: dict[str, Any], tag_details: dict[str, Any]) -> int | None:
    candidates: list[int] = []
    direct = tag_details.get("context_length")
    if isinstance(direct, int) and not isinstance(direct, bool) and direct > 0:
        candidates.append(direct)
    model_info = show.get("model_info")
    if isinstance(model_info, dict):
        for key, value in model_info.items():
            if (
                isinstance(key, str)
                and key.endswith(".context_length")
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
            ):
                candidates.append(value)
    return max(candidates) if candidates else None


def _placement(size: int | None, accelerator_size: int | None) -> tuple[str, float | None]:
    if accelerator_size is None or size is None or size <= 0:
        return "unknown", None
    fraction = min(1.0, max(0.0, accelerator_size / size))
    if accelerator_size <= 0:
        return "cpu", fraction
    if fraction >= 0.98:
        return "accelerator", fraction
    return "split", fraction


def _selected_model(
    tag: str,
    installed: dict[str, Any],
    show: dict[str, Any],
    running_models: list[dict[str, Any]],
) -> SelectedModelSnapshot:
    details = installed.get("details") if isinstance(installed.get("details"), dict) else {}
    show_details = show.get("details") if isinstance(show.get("details"), dict) else {}
    running = next(
        (
            item
            for item in running_models
            if isinstance(item, dict) and (item.get("model") == tag or item.get("name") == tag)
        ),
        None,
    )
    loaded_size = running.get("size") if running and isinstance(running.get("size"), int) else None
    accelerator_size = (
        running.get("size_vram") if running and isinstance(running.get("size_vram"), int) else None
    )
    placement, fraction = _placement(loaded_size, accelerator_size)
    capabilities = show.get("capabilities")
    return SelectedModelSnapshot(
        tag=tag,
        name=str(installed.get("name") or tag)[:300],
        digest=str(installed.get("digest"))[:200] if installed.get("digest") else None,
        size_bytes=installed.get("size") if isinstance(installed.get("size"), int) else None,
        parameter_size=(details.get("parameter_size") or show_details.get("parameter_size")),
        quantization_level=(details.get("quantization_level") or show_details.get("quantization_level")),
        family=(details.get("family") or show_details.get("family")),
        capabilities=[str(value)[:100] for value in capabilities if isinstance(value, str)]
        if isinstance(capabilities, list)
        else [],
        native_context_length=_native_context_length(show, details),
        loaded=running is not None,
        loaded_size_bytes=loaded_size,
        accelerator_size_bytes=accelerator_size,
        accelerator_fraction=round(fraction, 4) if fraction is not None else None,
        allocated_context_length=(
            running.get("context_length")
            if running and isinstance(running.get("context_length"), int)
            else None
        ),
        placement=placement,
        expires_at=str(running.get("expires_at"))[:100] if running and running.get("expires_at") else None,
    )


def probe_ollama(
    configured_endpoint: str,
    runtime_kind: str,
    requested_model_tag: str | None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProbeResult:
    relationship = classify_endpoint(configured_endpoint, runtime_kind)
    visibility = "full" if relationship == "same_runtime" else "partial" if relationship != "unknown" else "unknown"
    endpoint_display = safe_endpoint_display(configured_endpoint)
    try:
        base_url = _validate_base_url(configured_endpoint)
        timeout = httpx.Timeout(6.0, connect=2.0)
        with httpx.Client(base_url=base_url, timeout=timeout, transport=transport) as client:
            tags_payload = _get_json(client, "/api/tags")
            models_value = tags_payload.get("models", [])
            if not isinstance(models_value, list):
                raise ValueError("invalid model list")
            installed_models = [item for item in models_value if isinstance(item, dict)]

            version = None
            try:
                version_value = _get_json(client, "/api/version").get("version")
                version = str(version_value)[:100] if version_value is not None else None
            except (httpx.HTTPError, ValueError):
                pass

            running_models: list[dict[str, Any]] = []
            try:
                running_value = _get_json(client, "/api/ps").get("models", [])
                if isinstance(running_value, list):
                    running_models = [item for item in running_value if isinstance(item, dict)]
            except (httpx.HTTPError, ValueError):
                pass

            selected = None
            installed_match = None
            if requested_model_tag:
                installed_match = next(
                    (
                        item
                        for item in installed_models
                        if item.get("model") == requested_model_tag or item.get("name") == requested_model_tag
                    ),
                    None,
                )
                if installed_match is not None:
                    show: dict[str, Any] = {}
                    try:
                        show = _post_json(client, "/api/show", {"model": requested_model_tag})
                    except (httpx.HTTPError, ValueError):
                        pass
                    selected = _selected_model(requested_model_tag, installed_match, show, running_models)

            return ProbeResult(
                endpoint=OllamaEndpointSnapshot(
                    endpoint=endpoint_display,
                    relationship=relationship,
                    hardware_visibility=visibility,
                    reachable=True,
                    version=version,
                    installed_model_count=len(installed_models),
                ),
                selected_model=selected,
                requested_model_installed=(installed_match is not None if requested_model_tag else None),
            )
    except (httpx.HTTPError, ValueError) as exc:
        return ProbeResult(
            endpoint=OllamaEndpointSnapshot(
                endpoint=endpoint_display,
                relationship=relationship,
                hardware_visibility=visibility,
                reachable=False,
                error=_discovery_error(exc),
            ),
            selected_model=None,
            requested_model_installed=None,
        )
