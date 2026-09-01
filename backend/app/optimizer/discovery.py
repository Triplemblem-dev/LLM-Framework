from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.config import settings
from app.optimizer.adapters import inspect_runtime_host
from app.optimizer.ollama_probe import probe_ollama
from app.optimizer.schemas import (
    CapabilityStatus,
    DiscoveryWarning,
    OptimizerCapabilitiesOut,
    WarningSeverity,
)


def _warning(
    code: str,
    severity: WarningSeverity,
    title: str,
    detail: str,
    action: str | None = None,
) -> DiscoveryWarning:
    return DiscoveryWarning(code=code, severity=severity, title=title, detail=detail, action=action)


def discover_capabilities(requested_model_tag: str | None = None) -> OptimizerCapabilitiesOut:
    runtime = inspect_runtime_host()
    probe = probe_ollama(settings.ollama_host, runtime.runtime_kind, requested_model_tag)
    relationship = probe.endpoint.relationship
    if relationship == "same_runtime":
        runtime.applies_to_ollama_device = "yes"
    elif relationship in {"container_service", "native_host", "remote"}:
        runtime.applies_to_ollama_device = "no"
    else:
        runtime.applies_to_ollama_device = "unknown"

    warnings: list[DiscoveryWarning] = []
    if not probe.endpoint.reachable and probe.endpoint.error is not None:
        warnings.append(
            _warning(
                probe.endpoint.error.code,
                "error",
                "Ollama is not reachable",
                probe.endpoint.error.message,
                probe.endpoint.error.action,
            )
        )

    if relationship == "native_host" and runtime.runtime_kind == "container":
        warnings.append(
            _warning(
                "native_host_partial_visibility",
                "warning",
                "Native Ollama host is only partly visible",
                "The framework is running in a container while Ollama runs on the host. Container CPU, memory, and storage values are not treated as host hardware.",
                "Use the Ollama placement data below. A narrow host probe can provide full host metrics in a later slice.",
            )
        )
    elif relationship == "container_service":
        warnings.append(
            _warning(
                "ollama_container_partial_visibility",
                "info",
                "Ollama runs in another container",
                "The report can inspect Ollama model placement, but this backend container's resource limits and accelerator visibility may differ from the Ollama container.",
            )
        )
    elif relationship == "remote":
        warnings.append(
            _warning(
                "remote_hardware_unverified",
                "warning",
                "Remote Ollama hardware is not inspected",
                "The runtime values in this report describe the framework host, not the remote Ollama computer.",
                "Run a future authenticated host probe on the Ollama device for full hardware metrics.",
            )
        )

    try:
        parsed = urlsplit(settings.ollama_host)
        if relationship == "remote" and parsed.scheme == "http":
            warnings.append(
                _warning(
                    "remote_ollama_plain_http",
                    "warning",
                    "Remote Ollama connection is not encrypted",
                    "OLLAMA_HOST uses plain HTTP for a non-local endpoint.",
                    "Use a trusted private network or an authenticated TLS reverse proxy before sending prompts.",
                )
            )
    except ValueError:
        pass

    if probe.endpoint.reachable and requested_model_tag is None:
        warnings.append(
            _warning(
                "no_model_selected",
                "info",
                "No model selected for inspection",
                "Ollama is reachable, but detailed model context and placement require selecting an installed model.",
            )
        )
    elif probe.endpoint.reachable and probe.requested_model_installed is False:
        warnings.append(
            _warning(
                "requested_model_not_installed",
                "warning",
                "Selected model is not installed",
                f"Ollama did not report {requested_model_tag!r} in its installed model list.",
                "Select an installed model and refresh the report.",
            )
        )

    selected = probe.selected_model
    if selected is not None and not selected.loaded:
        warnings.append(
            _warning(
                "model_not_loaded",
                "info",
                "Model is installed but not currently loaded",
                "Memory allocation, active context, and processor placement become available after Ollama loads this model. Discovery does not load it.",
                "Send a normal prompt or run the controlled baseline benchmark, then refresh.",
            )
        )
    elif selected is not None and selected.placement == "cpu":
        warnings.append(
            _warning(
                "model_cpu_only",
                "warning",
                "Loaded model is using CPU memory only",
                "Ollama reports no accelerator-resident bytes for this loaded model, which usually reduces generation speed.",
                "Verify GPU/Metal support and the deployment mode before benchmarking.",
            )
        )
    elif selected is not None and selected.placement == "split":
        fraction = round((selected.accelerator_fraction or 0) * 100)
        warnings.append(
            _warning(
                "model_split_placement",
                "warning",
                "Loaded model is split between CPU and accelerator",
                f"Approximately {fraction}% of the loaded allocation is accelerator-resident.",
                "A smaller model, quantization, or context may improve generation speed; run a benchmark to measure this.",
            )
        )

    accelerator_metrics_apply = runtime.applies_to_ollama_device == "yes" and bool(runtime.accelerators)
    has_power = accelerator_metrics_apply and any(item.power_watts is not None for item in runtime.accelerators)
    has_temperature = accelerator_metrics_apply and any(
        item.temperature_celsius is not None for item in runtime.accelerators
    )
    if runtime.applies_to_ollama_device == "yes":
        hardware_status = "available"
        hardware_detail = "Runtime CPU, memory, storage, and accelerator observations describe the Ollama device."
    elif probe.endpoint.reachable:
        hardware_status = "partial"
        hardware_detail = "Ollama API evidence is available, but runtime hardware values do not fully describe the Ollama device."
    else:
        hardware_status = "unavailable"
        hardware_detail = "Neither runtime hardware nor reachable Ollama evidence describes the actual Ollama device."

    runtime_fields_available = runtime.memory.total_bytes is not None and runtime.cpu.logical_cores is not None
    capabilities = [
        CapabilityStatus(
            key="runtime_hardware",
            label="Framework runtime hardware",
            status="available" if runtime_fields_available else "partial",
            detail="Read-only OS, CPU, memory, storage, and supported accelerator fields were inspected."
            if runtime_fields_available
            else "Only part of the framework runtime hardware could be read on this platform.",
            source="framework runtime adapters",
        ),
        CapabilityStatus(
            key="ollama_api",
            label="Ollama API",
            status="available" if probe.endpoint.reachable else "unavailable",
            detail="Installed model and running-model APIs are reachable."
            if probe.endpoint.reachable
            else "No Ollama model data could be read.",
            source="configured Ollama API",
        ),
        CapabilityStatus(
            key="ollama_device_hardware",
            label="Actual Ollama-device hardware",
            status=hardware_status,
            detail=hardware_detail,
            source="runtime relationship plus Ollama placement",
        ),
        CapabilityStatus(
            key="selected_model_details",
            label="Selected model details",
            status="available" if selected is not None else "unavailable",
            detail="Model metadata and any loaded allocation were inspected."
            if selected is not None
            else "Select an installed, reachable model for model-specific details.",
            source="Ollama /api/tags, /api/show, and /api/ps",
        ),
        CapabilityStatus(
            key="power_metrics",
            label="Power metrics",
            status="available" if has_power else "unavailable",
            detail="A supported sensor reported current accelerator power."
            if has_power
            else "No trustworthy power reading for the actual Ollama device is available.",
            source="allow-listed platform adapter",
        ),
        CapabilityStatus(
            key="temperature_metrics",
            label="Temperature metrics",
            status="available" if has_temperature else "unavailable",
            detail="A supported sensor reported current accelerator temperature."
            if has_temperature
            else "No temperature reading for the actual Ollama device is available.",
            source="allow-listed platform adapter",
        ),
        CapabilityStatus(
            key="persistent_changes",
            label="Persistent configuration changes",
            status="unsupported",
            detail="The capability report and baseline benchmark are measurement-only. They cannot change model, Ollama, container, or operating-system settings.",
            source="optimizer measurement-only safety boundary",
        ),
    ]

    return OptimizerCapabilitiesOut(
        captured_at=datetime.now(timezone.utc),
        requested_model_tag=requested_model_tag,
        runtime_host=runtime,
        ollama=probe.endpoint,
        selected_model=selected,
        capabilities=capabilities,
        warnings=warnings,
    )
