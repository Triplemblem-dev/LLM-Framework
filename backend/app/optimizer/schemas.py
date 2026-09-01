from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Availability = Literal["available", "partial", "unavailable", "unsupported"]
WarningSeverity = Literal["info", "warning", "error"]


class DiscoveryWarning(BaseModel):
    code: str
    severity: WarningSeverity
    title: str
    detail: str
    action: str | None = None


class DiscoveryError(BaseModel):
    code: str
    message: str
    action: str


class CpuSnapshot(BaseModel):
    model: str | None = None
    architecture: str
    logical_cores: int | None = None
    physical_cores: int | None = None


class MemorySnapshot(BaseModel):
    total_bytes: int | None = None
    available_bytes: int | None = None
    swap_total_bytes: int | None = None
    swap_used_bytes: int | None = None


class StorageSnapshot(BaseModel):
    observed_path: str
    total_bytes: int | None = None
    available_bytes: int | None = None


class AcceleratorSnapshot(BaseModel):
    vendor: Literal["apple", "nvidia", "amd", "unknown"]
    name: str
    compute_backend: str | None = None
    memory_kind: Literal["dedicated", "unified", "shared", "unknown"]
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    utilization_percent: float | None = None
    power_watts: float | None = None
    temperature_celsius: float | None = None
    driver_version: str | None = None
    source: str


class RuntimeHostSnapshot(BaseModel):
    source: Literal["framework_runtime"] = "framework_runtime"
    runtime_kind: Literal["native", "container"]
    applies_to_ollama_device: Literal["yes", "no", "partial", "unknown"]
    os_name: str
    os_release: str
    cpu: CpuSnapshot
    memory: MemorySnapshot
    storage: StorageSnapshot
    accelerators: list[AcceleratorSnapshot] = Field(default_factory=list)


class OllamaEndpointSnapshot(BaseModel):
    endpoint: str
    relationship: Literal[
        "same_runtime", "container_service", "native_host", "remote", "unknown"
    ]
    hardware_visibility: Literal["full", "partial", "unknown"]
    reachable: bool
    version: str | None = None
    installed_model_count: int | None = None
    error: DiscoveryError | None = None


class SelectedModelSnapshot(BaseModel):
    tag: str
    name: str
    digest: str | None = None
    size_bytes: int | None = None
    parameter_size: str | None = None
    quantization_level: str | None = None
    family: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    native_context_length: int | None = None
    loaded: bool = False
    loaded_size_bytes: int | None = None
    accelerator_size_bytes: int | None = None
    accelerator_fraction: float | None = None
    allocated_context_length: int | None = None
    placement: Literal["cpu", "accelerator", "split", "unknown"] = "unknown"
    expires_at: str | None = None


class CapabilityStatus(BaseModel):
    key: str
    label: str
    status: Availability
    detail: str
    source: str


class OptimizerCapabilitiesOut(BaseModel):
    schema_version: Literal["1"] = "1"
    captured_at: datetime
    read_only: Literal[True] = True
    requested_model_tag: str | None = None
    runtime_host: RuntimeHostSnapshot
    ollama: OllamaEndpointSnapshot
    selected_model: SelectedModelSnapshot | None = None
    capabilities: list[CapabilityStatus]
    warnings: list[DiscoveryWarning]


OptimizerRunState = Literal[
    "planned",
    "queued",
    "detecting",
    "warming",
    "measuring",
    "evaluating",
    "completed",
    "cancelled",
    "failed",
]
OptimizerObjective = Literal["balanced", "fast_response", "large_context", "low_memory", "low_energy"]
OptimizerMode = Literal["quick", "standard"]
OptimizerBenchmarkKind = Literal["baseline", "context_comparison"]


class OptimizationRunCreate(BaseModel):
    model_tag: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$",
    )
    objective: OptimizerObjective = "balanced"
    mode: OptimizerMode = "quick"
    benchmark_kind: OptimizerBenchmarkKind = "baseline"


class OptimizationMeasurementOut(BaseModel):
    id: str
    trial_index: int
    workload_case: str
    is_warmup: bool
    cold_load: bool | None
    state: str
    ttft_ms: float | None
    prompt_tokens: int | None
    generated_tokens: int | None
    prompt_tokens_per_second: float | None
    generation_tokens_per_second: float | None
    load_duration_ms: float | None
    total_duration_ms: float | None
    wall_duration_ms: float | None
    output_characters: int
    finish_reason: str | None
    placement: dict[str, Any] | None
    resource_snapshot: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class OptimizationCandidateOut(BaseModel):
    id: str
    label: str
    settings: dict[str, Any]
    state: str
    measurements: list[OptimizationMeasurementOut]


class OptimizationRunOut(BaseModel):
    schema_version: Literal["1"] = "1"
    id: str
    model_tag: str
    benchmark_kind: OptimizerBenchmarkKind
    objective: OptimizerObjective
    mode: OptimizerMode
    workload_version: str
    runner_version: str
    endpoint_display: str
    state: OptimizerRunState
    current_stage_detail: str | None
    total_trials: int
    completed_trials: int
    cancel_requested: bool
    ollama_version: str | None
    hardware_snapshot: dict[str, Any] | None
    summary: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    estimated_seconds: int
    disruption_notice: str
    candidates: list[OptimizationCandidateOut]


class ContextApplyIssue(BaseModel):
    code: str
    title: str
    detail: str
    action: str | None = None


class ContextApplyEvidence(BaseModel):
    score_version: str | None = None
    runner_version: str
    run_completed_at: datetime | None = None
    measured_trials: int
    confidence: str
    endpoint_status: Literal["match", "changed"]
    model_digest_status: Literal["match", "changed", "unavailable"]
    ollama_version_status: Literal["match", "changed", "unavailable"]
    hardware_status: Literal["match", "changed", "partial", "unavailable"]
    hardware_visibility: Literal["full", "partial", "unknown"]


class ContextApplyPreviewOut(BaseModel):
    schema_version: Literal["1"] = "1"
    preview_version: str
    run_id: str
    status: Literal["ready", "blocked", "no_change"]
    can_apply: bool
    setting_scope: Literal["model_profile"] = "model_profile"
    model_tag: str
    profile_id: str | None = None
    profile_active: bool
    current_context_length: int | None = None
    recommended_context_length: int | None = None
    target_context_length: int | None = None
    selection_kind: Literal["recommended", "measured_candidate", "custom", "unavailable"]
    delta_tokens: int | None = None
    native_context_limit: int | None = None
    safety_ceiling: int
    effect_timing: Literal["next_model_request"] = "next_model_request"
    restart_required: Literal[False] = False
    affected_scope: str
    blocking_reasons: list[ContextApplyIssue]
    warnings: list[ContextApplyIssue]
    checked_at: datetime
    evidence: ContextApplyEvidence


class ContextApplyRequest(BaseModel):
    confirmation: Literal["apply_recommended_context"]
    preview_version: str = Field(min_length=1, max_length=100)
    expected_current_context_length: int = Field(ge=512, le=262_144)
    target_context_length: int = Field(ge=512, le=262_144)
    acknowledged_warning_codes: list[str] = Field(default_factory=list, max_length=30)


class ContextRollbackRequest(BaseModel):
    confirmation: Literal["rollback_context_change"]
    expected_current_context_length: int = Field(ge=512, le=262_144)


class ContextAuditOut(BaseModel):
    id: str
    run_id: str | None
    source_audit_id: str | None
    model_tag: str
    action: Literal["apply", "rollback"]
    previous_context_length: int
    new_context_length: int
    effective_context_length: int
    preview_version: str
    score_version: str | None
    runner_version: str
    acknowledged_warning_codes: list[str]
    rollback_available: bool
    created_at: datetime


class ContextChangeResultOut(BaseModel):
    schema_version: Literal["1"] = "1"
    verified: Literal[True] = True
    profile_active: bool
    effective_context_length: int
    effect_timing: Literal["next_model_request"] = "next_model_request"
    restart_required: Literal[False] = False
    audit: ContextAuditOut
