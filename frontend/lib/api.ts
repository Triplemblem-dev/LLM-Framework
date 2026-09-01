import {
  ChatMessage,
  Citation,
  CodeRepositoryInfo,
  ConversationDetail,
  Conversation,
  Domain,
  DomainModelSettings,
  DocumentInfo,
  DocumentPreview,
  DocumentOrganizationPreview,
  DocumentOrganizationSuggestion,
  GenerationMetrics,
  InheritancePolicy,
  InheritedDocumentInfo,
  InheritedMemoryInfo,
  LearningCardSet,
  MemoryInfo,
  ModelInfo,
  ModelProfile,
  OptimizerContextApplyPreview,
  OptimizerContextAudit,
  OptimizerContextChangeResult,
  OptimizerReport,
  OptimizerBenchmarkKind,
  OptimizerMode,
  OptimizerObjective,
  OptimizerRun,
  PromptLayer,
  RemoteAccessMode,
  RemoteAccessStatus,
  RemoteApiKey,
  RemoteApiKeyCreated,
  RemoteConnectionTest,
  SubDomain,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "llmf_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, tokenOverride?: string): Promise<T> {
  const token = tokenOverride ?? getToken();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function verifyToken(token: string): Promise<boolean> {
  try {
    await request("/auth/verify", {}, token);
    return true;
  } catch {
    return false;
  }
}

// --- Optional remote access ---

function mapRemoteStatus(raw: any): RemoteAccessStatus {
  return {
    mode: raw.mode,
    gatewayPort: raw.gateway_port,
    gatewayConfigured: raw.gateway_configured,
    gatewayRunning: raw.gateway_running,
    apiBaseUrl: raw.api_base_url,
    bindAddress: raw.bind_address,
    hostname: raw.hostname,
    networkConfigurationValid: raw.network_configuration_valid,
    networkConfigurationError: raw.network_configuration_error,
    tailscaleConfigured: raw.tailscale_configured,
    certificateAvailable: raw.certificate_available,
    activeKeyCount: raw.active_key_count,
  };
}

function mapRemoteKey(raw: any): RemoteApiKey {
  return {
    id: raw.id,
    name: raw.name,
    tokenPrefix: raw.token_prefix,
    domainIds: raw.domain_ids ?? [],
    requestsPerMinute: raw.requests_per_minute,
    expiresAt: raw.expires_at,
    revokedAt: raw.revoked_at,
    lastUsedAt: raw.last_used_at,
    createdAt: raw.created_at,
  };
}

export async function getRemoteAccess(): Promise<RemoteAccessStatus> {
  return mapRemoteStatus(await request<any>("/remote-access"));
}

export async function updateRemoteAccess(mode: RemoteAccessMode, gatewayPort = 8443): Promise<RemoteAccessStatus> {
  return mapRemoteStatus(await request<any>("/remote-access", {
    method: "PUT",
    body: JSON.stringify({ mode, gateway_port: gatewayPort }),
  }));
}

export async function listRemoteApiKeys(): Promise<RemoteApiKey[]> {
  return (await request<any[]>("/remote-access/keys")).map(mapRemoteKey);
}

export async function createRemoteApiKey(
  name: string,
  domainIds: string[],
  requestsPerMinute = 30,
): Promise<RemoteApiKeyCreated> {
  const raw = await request<any>("/remote-access/keys", {
    method: "POST",
    body: JSON.stringify({ name, domain_ids: domainIds, requests_per_minute: requestsPerMinute }),
  });
  return { ...mapRemoteKey(raw), token: raw.token };
}

export async function revokeRemoteApiKey(keyId: string): Promise<void> {
  await request(`/remote-access/keys/${keyId}`, { method: "DELETE" });
}

export async function testRemoteConnection(): Promise<RemoteConnectionTest> {
  const raw = await request<any>("/remote-access/connection-test", { method: "POST" });
  return {
    ready: raw.ready,
    mode: raw.mode,
    gatewayConfigured: raw.gateway_configured,
    gatewayRunning: raw.gateway_running,
    networkConfigurationValid: raw.network_configuration_valid,
    detail: raw.detail,
  };
}

export async function getRemoteGatewayCertificate(): Promise<Blob> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${BASE_URL}/remote-access/certificate`, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? `Request failed (${response.status})`);
  }
  return response.blob();
}

// --- Models ---

function mapModelInfo(raw: any): ModelInfo {
  return {
    tag: raw.tag,
    name: raw.name,
    sizeBytes: raw.size_bytes,
    parameterSize: raw.parameter_size,
    quantizationLevel: raw.quantization_level,
    contextLength: raw.context_length,
    modifiedAt: raw.modified_at,
  };
}

function mapModelProfile(raw: any): ModelProfile {
  return {
    id: raw.id,
    tag: raw.ollama_tag,
    name: raw.name,
    contextLength: raw.context_length,
    temperature: raw.temperature,
    topP: raw.top_p,
    topK: raw.top_k,
    repeatPenalty: raw.repeat_penalty,
  };
}

export async function listInstalledModels(): Promise<ModelInfo[]> {
  const raw = await request<any[]>("/models/installed");
  return raw.map(mapModelInfo);
}

export async function getActiveModelProfile(): Promise<ModelProfile | null> {
  const raw = await request<any | null>("/models/profile");
  return raw ? mapModelProfile(raw) : null;
}

export async function setActiveModelProfile(tag: string): Promise<ModelProfile> {
  const raw = await request<any>("/models/profile", {
    method: "PUT",
    body: JSON.stringify({ ollama_tag: tag }),
  });
  return mapModelProfile(raw);
}

function mapDomainModelSettings(raw: any): DomainModelSettings {
  return {
    domainId: raw.domain_id,
    modelTag: raw.model_tag,
    contextLength: raw.context_length,
    maxOutputTokens: raw.max_output_tokens,
    temperature: raw.temperature,
    topP: raw.top_p,
    topK: raw.top_k,
    repeatPenalty: raw.repeat_penalty,
    source: raw.source,
    nativeContextLength: raw.native_context_length,
    detectedAllocatedContextLength: raw.detected_allocated_context_length,
    recommendedContextLength: raw.recommended_context_length,
    recommendationBasis: raw.recommendation_basis,
  };
}

export async function getDomainModelSettings(domainId: string): Promise<DomainModelSettings> {
  return mapDomainModelSettings(await request<any>(`/domains/${domainId}/model-settings`));
}

export async function updateDomainModelSettings(
  domainId: string,
  settings: Omit<DomainModelSettings, "domainId" | "source" | "nativeContextLength" | "detectedAllocatedContextLength" | "recommendedContextLength" | "recommendationBasis">
): Promise<DomainModelSettings> {
  return mapDomainModelSettings(await request<any>(`/domains/${domainId}/model-settings`, {
    method: "PUT",
    body: JSON.stringify({
      model_tag: settings.modelTag,
      context_length: settings.contextLength,
      max_output_tokens: settings.maxOutputTokens,
      temperature: settings.temperature,
      top_p: settings.topP,
      top_k: settings.topK,
      repeat_penalty: settings.repeatPenalty,
    }),
  }));
}

// --- Model Performance Optimizer ---

function mapOptimizerReport(raw: any): OptimizerReport {
  return {
    schemaVersion: raw.schema_version,
    capturedAt: raw.captured_at,
    readOnly: raw.read_only,
    requestedModelTag: raw.requested_model_tag,
    runtimeHost: {
      source: raw.runtime_host.source,
      runtimeKind: raw.runtime_host.runtime_kind,
      appliesToOllamaDevice: raw.runtime_host.applies_to_ollama_device,
      osName: raw.runtime_host.os_name,
      osRelease: raw.runtime_host.os_release,
      cpu: {
        model: raw.runtime_host.cpu.model,
        architecture: raw.runtime_host.cpu.architecture,
        logicalCores: raw.runtime_host.cpu.logical_cores,
        physicalCores: raw.runtime_host.cpu.physical_cores,
      },
      memory: {
        totalBytes: raw.runtime_host.memory.total_bytes,
        availableBytes: raw.runtime_host.memory.available_bytes,
        swapTotalBytes: raw.runtime_host.memory.swap_total_bytes,
        swapUsedBytes: raw.runtime_host.memory.swap_used_bytes,
      },
      storage: {
        observedPath: raw.runtime_host.storage.observed_path,
        totalBytes: raw.runtime_host.storage.total_bytes,
        availableBytes: raw.runtime_host.storage.available_bytes,
      },
      accelerators: (raw.runtime_host.accelerators ?? []).map((item: any) => ({
        vendor: item.vendor,
        name: item.name,
        computeBackend: item.compute_backend,
        memoryKind: item.memory_kind,
        memoryTotalBytes: item.memory_total_bytes,
        memoryUsedBytes: item.memory_used_bytes,
        utilizationPercent: item.utilization_percent,
        powerWatts: item.power_watts,
        temperatureCelsius: item.temperature_celsius,
        driverVersion: item.driver_version,
        source: item.source,
      })),
    },
    ollama: {
      endpoint: raw.ollama.endpoint,
      relationship: raw.ollama.relationship,
      hardwareVisibility: raw.ollama.hardware_visibility,
      reachable: raw.ollama.reachable,
      version: raw.ollama.version,
      installedModelCount: raw.ollama.installed_model_count,
      error: raw.ollama.error,
    },
    selectedModel: raw.selected_model
      ? {
          tag: raw.selected_model.tag,
          name: raw.selected_model.name,
          digest: raw.selected_model.digest,
          sizeBytes: raw.selected_model.size_bytes,
          parameterSize: raw.selected_model.parameter_size,
          quantizationLevel: raw.selected_model.quantization_level,
          family: raw.selected_model.family,
          capabilities: raw.selected_model.capabilities ?? [],
          nativeContextLength: raw.selected_model.native_context_length,
          loaded: raw.selected_model.loaded,
          loadedSizeBytes: raw.selected_model.loaded_size_bytes,
          acceleratorSizeBytes: raw.selected_model.accelerator_size_bytes,
          acceleratorFraction: raw.selected_model.accelerator_fraction,
          allocatedContextLength: raw.selected_model.allocated_context_length,
          placement: raw.selected_model.placement,
          expiresAt: raw.selected_model.expires_at,
        }
      : null,
    capabilities: (raw.capabilities ?? []).map((item: any) => ({
      key: item.key,
      label: item.label,
      status: item.status,
      detail: item.detail,
      source: item.source,
    })),
    warnings: (raw.warnings ?? []).map((item: any) => ({
      code: item.code,
      severity: item.severity,
      title: item.title,
      detail: item.detail,
      action: item.action,
    })),
  };
}

export async function getOptimizerCapabilities(modelTag?: string): Promise<OptimizerReport> {
  const query = modelTag ? `?${new URLSearchParams({ model_tag: modelTag })}` : "";
  return mapOptimizerReport(await request<any>(`/optimizer/capabilities${query}`));
}

function mapOptimizerPlacement(raw: any) {
  if (!raw) return null;
  return {
    kind: raw.kind,
    acceleratorFraction: raw.accelerator_fraction,
    loadedSizeBytes: raw.loaded_size_bytes,
    acceleratorSizeBytes: raw.accelerator_size_bytes,
    source: raw.source,
  };
}

function mapOptimizerRun(raw: any): OptimizerRun {
  const summary = raw.summary ?? {};
  return {
    schemaVersion: raw.schema_version,
    id: raw.id,
    modelTag: raw.model_tag,
    benchmarkKind: raw.benchmark_kind,
    objective: raw.objective,
    mode: raw.mode,
    workloadVersion: raw.workload_version,
    runnerVersion: raw.runner_version,
    endpointDisplay: raw.endpoint_display,
    state: raw.state,
    currentStageDetail: raw.current_stage_detail,
    totalTrials: raw.total_trials,
    completedTrials: raw.completed_trials,
    cancelRequested: raw.cancel_requested,
    ollamaVersion: raw.ollama_version,
    hardwareSnapshot: raw.hardware_snapshot ? mapOptimizerReport(raw.hardware_snapshot) : null,
    summary: {
      ...summary,
      latest_placement: mapOptimizerPlacement(summary.latest_placement),
      recommendation: summary.recommendation ? {
        ...summary.recommendation,
        candidate_results: (summary.recommendation.candidate_results ?? []).map((item: any) => ({
          ...item,
          placement: mapOptimizerPlacement(item.placement),
        })),
      } : undefined,
    },
    errorCode: raw.error_code,
    errorMessage: raw.error_message,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    estimatedSeconds: raw.estimated_seconds,
    disruptionNotice: raw.disruption_notice,
    candidates: (raw.candidates ?? []).map((candidate: any) => ({
      id: candidate.id,
      label: candidate.label,
      settings: candidate.settings ?? {},
      state: candidate.state,
      measurements: (candidate.measurements ?? []).map((item: any) => ({
        id: item.id,
        trialIndex: item.trial_index,
        workloadCase: item.workload_case,
        isWarmup: item.is_warmup,
        coldLoad: item.cold_load,
        state: item.state,
        ttftMs: item.ttft_ms,
        promptTokens: item.prompt_tokens,
        generatedTokens: item.generated_tokens,
        promptTokensPerSecond: item.prompt_tokens_per_second,
        generationTokensPerSecond: item.generation_tokens_per_second,
        loadDurationMs: item.load_duration_ms,
        totalDurationMs: item.total_duration_ms,
        wallDurationMs: item.wall_duration_ms,
        outputCharacters: item.output_characters,
        finishReason: item.finish_reason,
        placement: mapOptimizerPlacement(item.placement),
        resourceSnapshot: item.resource_snapshot,
        errorCode: item.error_code,
        errorMessage: item.error_message,
        startedAt: item.started_at,
        completedAt: item.completed_at,
      })),
    })),
  };
}

export async function createOptimizerRun(
  modelTag: string,
  objective: OptimizerObjective,
  mode: OptimizerMode,
  benchmarkKind: OptimizerBenchmarkKind,
): Promise<OptimizerRun> {
  return mapOptimizerRun(await request<any>("/optimizer/runs", {
    method: "POST",
    body: JSON.stringify({ model_tag: modelTag, objective, mode, benchmark_kind: benchmarkKind }),
  }));
}

export async function listOptimizerRuns(): Promise<OptimizerRun[]> {
  return (await request<any[]>("/optimizer/runs")).map(mapOptimizerRun);
}

export async function getOptimizerRun(runId: string): Promise<OptimizerRun> {
  return mapOptimizerRun(await request<any>(`/optimizer/runs/${runId}`));
}

export async function getOptimizerContextApplyPreview(
  runId: string,
  targetContextLength?: number,
): Promise<OptimizerContextApplyPreview> {
  const query = targetContextLength === undefined
    ? ""
    : `?${new URLSearchParams({ target_context_length: String(targetContextLength) })}`;
  const raw = await request<any>(`/optimizer/runs/${runId}/context-apply-preview${query}`);
  const mapIssue = (item: any) => ({
    code: item.code,
    title: item.title,
    detail: item.detail,
    action: item.action,
  });
  return {
    schemaVersion: raw.schema_version,
    previewVersion: raw.preview_version,
    runId: raw.run_id,
    status: raw.status,
    canApply: raw.can_apply,
    settingScope: raw.setting_scope,
    modelTag: raw.model_tag,
    profileId: raw.profile_id,
    profileActive: raw.profile_active,
    currentContextLength: raw.current_context_length,
    recommendedContextLength: raw.recommended_context_length,
    targetContextLength: raw.target_context_length,
    selectionKind: raw.selection_kind,
    deltaTokens: raw.delta_tokens,
    nativeContextLimit: raw.native_context_limit,
    safetyCeiling: raw.safety_ceiling,
    effectTiming: raw.effect_timing,
    restartRequired: raw.restart_required,
    affectedScope: raw.affected_scope,
    blockingReasons: (raw.blocking_reasons ?? []).map(mapIssue),
    warnings: (raw.warnings ?? []).map(mapIssue),
    checkedAt: raw.checked_at,
    evidence: {
      scoreVersion: raw.evidence.score_version,
      runnerVersion: raw.evidence.runner_version,
      runCompletedAt: raw.evidence.run_completed_at,
      measuredTrials: raw.evidence.measured_trials,
      confidence: raw.evidence.confidence,
      endpointStatus: raw.evidence.endpoint_status,
      modelDigestStatus: raw.evidence.model_digest_status,
      ollamaVersionStatus: raw.evidence.ollama_version_status,
      hardwareStatus: raw.evidence.hardware_status,
      hardwareVisibility: raw.evidence.hardware_visibility,
    },
  };
}

function mapOptimizerContextAudit(raw: any): OptimizerContextAudit {
  return {
    id: raw.id,
    runId: raw.run_id,
    sourceAuditId: raw.source_audit_id,
    modelTag: raw.model_tag,
    action: raw.action,
    previousContextLength: raw.previous_context_length,
    newContextLength: raw.new_context_length,
    effectiveContextLength: raw.effective_context_length,
    previewVersion: raw.preview_version,
    scoreVersion: raw.score_version,
    runnerVersion: raw.runner_version,
    acknowledgedWarningCodes: raw.acknowledged_warning_codes ?? [],
    rollbackAvailable: raw.rollback_available,
    createdAt: raw.created_at,
  };
}

function mapOptimizerContextChange(raw: any): OptimizerContextChangeResult {
  return {
    schemaVersion: raw.schema_version,
    verified: raw.verified,
    profileActive: raw.profile_active,
    effectiveContextLength: raw.effective_context_length,
    effectTiming: raw.effect_timing,
    restartRequired: raw.restart_required,
    audit: mapOptimizerContextAudit(raw.audit),
  };
}

export async function applyOptimizerContext(
  runId: string,
  preview: OptimizerContextApplyPreview,
): Promise<OptimizerContextChangeResult> {
  return mapOptimizerContextChange(await request<any>(`/optimizer/runs/${runId}/context-apply`, {
    method: "POST",
    body: JSON.stringify({
      confirmation: "apply_recommended_context",
      preview_version: preview.previewVersion,
      expected_current_context_length: preview.currentContextLength,
      target_context_length: preview.targetContextLength,
      acknowledged_warning_codes: preview.warnings.map((item) => item.code),
    }),
  }));
}

export async function listOptimizerContextAudits(modelTag?: string): Promise<OptimizerContextAudit[]> {
  const query = modelTag ? `?${new URLSearchParams({ model_tag: modelTag })}` : "";
  return (await request<any[]>(`/optimizer/context-audits${query}`)).map(mapOptimizerContextAudit);
}

export async function rollbackOptimizerContext(
  auditId: string,
  expectedCurrentContextLength: number,
): Promise<OptimizerContextChangeResult> {
  return mapOptimizerContextChange(await request<any>(`/optimizer/context-audits/${auditId}/rollback`, {
    method: "POST",
    body: JSON.stringify({
      confirmation: "rollback_context_change",
      expected_current_context_length: expectedCurrentContextLength,
    }),
  }));
}

export async function startOptimizerRun(runId: string): Promise<OptimizerRun> {
  return mapOptimizerRun(await request<any>(`/optimizer/runs/${runId}/start`, { method: "POST" }));
}

export async function cancelOptimizerRun(runId: string): Promise<OptimizerRun> {
  return mapOptimizerRun(await request<any>(`/optimizer/runs/${runId}/cancel`, { method: "POST" }));
}

export async function deleteOptimizerRun(runId: string): Promise<void> {
  await request(`/optimizer/runs/${runId}`, { method: "DELETE" });
}

export async function getOptimizerRunReport(runId: string): Promise<Blob> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${BASE_URL}/optimizer/runs/${runId}/export`, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? `Request failed (${response.status})`);
  }
  return response.blob();
}

// --- Domains ---

function mapSubDomain(raw: any): SubDomain {
  return {
    id: raw.id,
    name: raw.name,
    slug: raw.slug,
    description: raw.description,
    prompt: raw.prompt,
    inheritance: raw.inheritance,
    shareWithSiblings: raw.share_with_siblings,
  };
}

function mapDomain(raw: any): Domain {
  return {
    ...mapSubDomain(raw),
    expanded: false,
    subdomains: (raw.subdomains ?? []).map(mapSubDomain),
  };
}

export async function listDomains(): Promise<Domain[]> {
  const raw = await request<any[]>("/domains");
  return raw.map(mapDomain);
}

export async function createDomain(name: string, prompt: string, description = ""): Promise<Domain> {
  const raw = await request<any>("/domains", {
    method: "POST",
    body: JSON.stringify({ name, prompt, description }),
  });
  return mapDomain(raw);
}

export async function createSubdomain(
  domainId: string,
  name: string,
  prompt: string,
  description = ""
): Promise<SubDomain> {
  const raw = await request<any>(`/domains/${domainId}/subdomains`, {
    method: "POST",
    body: JSON.stringify({ name, prompt, description }),
  });
  return mapSubDomain(raw);
}

export interface DomainPatch {
  name?: string;
  description?: string;
  prompt?: string;
  inheritance?: InheritancePolicy;
  shareWithSiblings?: boolean;
}

export async function updateDomain(id: string, patch: DomainPatch): Promise<SubDomain> {
  const { shareWithSiblings, ...rest } = patch;
  const body: Record<string, unknown> = { ...rest };
  if (shareWithSiblings !== undefined) body.share_with_siblings = shareWithSiblings;

  const raw = await request<any>(`/domains/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return mapSubDomain(raw);
}

export interface DeleteScopeResult {
  deletedScopeCount: number;
  storageCleanupComplete: boolean;
}

export async function deleteDomain(id: string): Promise<DeleteScopeResult> {
  const raw = await request<any>(`/domains/${id}`, { method: "DELETE" });
  return {
    deletedScopeCount: raw.deleted_scope_count,
    storageCleanupComplete: raw.storage_cleanup_complete,
  };
}

export async function promptPreview(
  domainId: string,
  draft: string,
  conversationId: string | null,
  signal?: AbortSignal
): Promise<PromptLayer[]> {
  const params = new URLSearchParams({ draft });
  if (conversationId) params.set("conversation_id", conversationId);
  const raw = await request<{ layers: any[] }>(`/domains/${domainId}/prompt-preview?${params}`, { signal });
  return raw.layers.map(mapPromptLayer);
}

export async function updatePromptLayerControl(
  domainId: string,
  layerKey: string,
  enabled: boolean,
  riskAcknowledged = false
): Promise<void> {
  await request(`/domains/${domainId}/prompt-layers/${encodeURIComponent(layerKey)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled, risk_acknowledged: riskAcknowledged }),
  });
}

function mapPromptLayer(raw: any): PromptLayer {
  return {
    key: raw.key,
    name: raw.name,
    category: raw.category,
    content: raw.content,
    applied: raw.applied,
    state: raw.state,
    reason: raw.reason,
    sourceType: raw.source_type,
    sourceName: raw.source_name,
    editTarget: raw.edit_target,
    modelRole: raw.model_role,
    control: raw.control,
    ownerEnabled: raw.owner_enabled,
  };
}

// --- Conversations ---

export async function listConversations(domainId: string): Promise<Conversation[]> {
  const raw = await request<any[]>(`/domains/${domainId}/conversations`);
  return raw.map((c) => ({ id: c.id, title: c.title }));
}

function mapCitation(raw: any): Citation {
  return {
    sourceType: raw.source_type ?? "document",
    documentId: raw.document_id,
    documentName: raw.document_name,
    scopeId: raw.scope_id,
    scopeName: raw.scope_name,
    heading: raw.heading,
    pageNumber: raw.page_number,
    chunkIndex: raw.chunk_index,
    repositoryId: raw.repository_id ?? null,
    repositoryName: raw.repository_name ?? null,
    revisionLabel: raw.revision_label ?? null,
    snapshotHash: raw.snapshot_hash ?? null,
    relativePath: raw.relative_path ?? null,
    startLine: raw.start_line ?? null,
    endLine: raw.end_line ?? null,
  };
}

function mapGenerationMetrics(raw: any): GenerationMetrics | null {
  if (!raw) return null;
  return {
    promptTokens: raw.prompt_tokens ?? null,
    outputTokens: raw.output_tokens ?? null,
    tokensPerSecond: raw.tokens_per_second ?? null,
    timeToFirstTokenMs: raw.time_to_first_token_ms ?? null,
    promptEvalDurationMs: raw.prompt_eval_duration_ms ?? null,
    generationDurationMs: raw.generation_duration_ms ?? null,
    loadDurationMs: raw.load_duration_ms ?? null,
    totalDurationMs: raw.total_duration_ms ?? null,
    finishReason: raw.finish_reason ?? null,
    status: raw.status ?? "completed",
  };
}

function mapLearningCardSet(raw: any): LearningCardSet | null {
  if (!raw) return null;
  return {
    sourceMessageId: raw.source_message_id,
    modelTag: raw.model_tag,
    createdAt: raw.created_at,
    title: raw.title,
    summary: raw.summary,
    cards: (raw.cards ?? []).map((card: any) => ({
      category: card.category,
      title: card.title,
      takeaway: card.takeaway,
    })),
  };
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const raw = await request<any>(`/conversations/${id}`);
  return {
    id: raw.id,
    title: raw.title,
    messages: raw.messages.map(
      (m: any): ChatMessage => ({
        id: m.id,
        role: m.role,
        text: m.content,
        citations: (m.citations ?? []).map(mapCitation),
        generationMetrics: mapGenerationMetrics(m.generation_metrics),
        learningCards: mapLearningCardSet(m.learning_cards),
      })
    ),
  };
}

export async function createLearningCards(conversationId: string): Promise<LearningCardSet> {
  const raw = await request<any>(`/conversations/${conversationId}/learning-cards`, {
    method: "POST",
  });
  return mapLearningCardSet(raw)!;
}

export async function deleteConversation(domainId: string, conversationId: string): Promise<void> {
  await request(`/domains/${domainId}/conversations/${conversationId}`, { method: "DELETE" });
}

// --- Documents ---

function mapDocument(raw: any): DocumentInfo {
  return {
    id: raw.id,
    filename: raw.filename,
    sourceType: raw.source_type,
    folderPath: raw.folder_path ?? "",
    tags: raw.tags ?? [],
    version: raw.version,
    status: raw.status,
    error: raw.error,
    chunkCount: raw.chunk_count,
    createdAt: raw.created_at,
    markdownAvailable: raw.markdown_available ?? false,
    markdownFilename: raw.markdown_filename ?? null,
  };
}

function mapInheritedDocument(raw: any): InheritedDocumentInfo {
  return { ...mapDocument(raw), scopeId: raw.scope_id, scopeName: raw.scope_name };
}

export async function listDocuments(domainId: string): Promise<DocumentInfo[]> {
  const raw = await request<any[]>(`/domains/${domainId}/documents`);
  return raw.map(mapDocument);
}

export async function listInheritedDocuments(domainId: string): Promise<InheritedDocumentInfo[]> {
  const raw = await request<any[]>(`/domains/${domainId}/documents/inherited`);
  return raw.map(mapInheritedDocument);
}

export async function uploadDocument(domainId: string, file: File): Promise<DocumentInfo> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/domains/${domainId}/documents`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? `Upload failed (${res.status})`);
  }
  return mapDocument(await res.json());
}

export async function deleteDocument(domainId: string, documentId: string): Promise<void> {
  await request(`/domains/${domainId}/documents/${documentId}`, { method: "DELETE" });
}

export async function createDocumentMarkdown(domainId: string, documentId: string): Promise<DocumentInfo> {
  const raw = await request<any>(`/domains/${domainId}/documents/${documentId}/markdown`, {
    method: "POST",
  });
  return mapDocument(raw);
}

export async function getDocumentPreview(
  domainId: string,
  documentId: string,
  variant: "source" | "markdown" = "source"
): Promise<DocumentPreview> {
  const raw = await request<any>(
    `/domains/${domainId}/documents/${documentId}/preview?variant=${encodeURIComponent(variant)}`
  );
  return {
    filename: raw.filename,
    sourceType: raw.source_type,
    format: raw.format,
    content: raw.content,
    characterCount: raw.character_count,
    truncated: raw.truncated,
    markdownCopy: raw.markdown_copy,
  };
}

export async function exportDocumentMarkdown(domainId: string, documentId: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}/domains/${domainId}/documents/${documentId}/markdown`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? `PDF conversion failed (${res.status})`);
  }
  return res.blob();
}

function mapOrganizationSuggestion(raw: any): DocumentOrganizationSuggestion {
  return {
    documentId: raw.document_id,
    filename: raw.filename,
    folderPath: raw.folder_path,
    tags: raw.tags ?? [],
    reason: raw.reason,
  };
}

export async function previewDocumentOrganization(
  domainId: string,
  modelTag: string | null
): Promise<DocumentOrganizationPreview> {
  const raw = await request<any>(`/domains/${domainId}/documents/organize/preview`, {
    method: "POST",
    body: JSON.stringify({ model_tag: modelTag }),
  });
  return {
    modelTag: raw.model_tag,
    documentSetHash: raw.document_set_hash,
    suggestions: (raw.suggestions ?? []).map(mapOrganizationSuggestion),
    warnings: raw.warnings ?? [],
  };
}

export async function applyDocumentOrganization(
  domainId: string,
  documentSetHash: string,
  suggestions: DocumentOrganizationSuggestion[]
): Promise<DocumentInfo[]> {
  const raw = await request<any[]>(`/domains/${domainId}/documents/organize/apply`, {
    method: "POST",
    body: JSON.stringify({
      document_set_hash: documentSetHash,
      suggestions: suggestions.map((item) => ({
        document_id: item.documentId,
        folder_path: item.folderPath,
        tags: item.tags,
      })),
      confirmation: "apply_document_organization",
    }),
  });
  return raw.map(mapDocument);
}

// --- Code repositories ---

function mapCodeRepository(raw: any): CodeRepositoryInfo {
  return {
    id: raw.id,
    scopeId: raw.scope_id,
    name: raw.name,
    archiveFilename: raw.archive_filename,
    revisionLabel: raw.revision_label,
    contentHash: raw.content_hash,
    status: raw.status,
    error: raw.error,
    fileCount: raw.file_count,
    skippedFileCount: raw.skipped_file_count,
    securityExcludedCount: raw.security_excluded_count,
    chunkCount: raw.chunk_count,
    exclusions: raw.exclusions ?? [],
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

export async function listRepositories(domainId: string): Promise<CodeRepositoryInfo[]> {
  const raw = await request<any[]>(`/domains/${domainId}/repositories`);
  return raw.map(mapCodeRepository);
}

async function sendRepositoryArchive(
  path: string,
  file: File,
  name?: string,
  revisionLabel?: string
): Promise<CodeRepositoryInfo> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  if (name) form.append("name", name);
  if (revisionLabel) form.append("revision_label", revisionLabel);
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? `Repository import failed (${res.status})`);
  }
  return mapCodeRepository(await res.json());
}

export function uploadRepository(
  domainId: string,
  file: File,
  name?: string,
  revisionLabel?: string
): Promise<CodeRepositoryInfo> {
  return sendRepositoryArchive(`/domains/${domainId}/repositories`, file, name, revisionLabel);
}

export function replaceRepository(
  domainId: string,
  repositoryId: string,
  file: File,
  revisionLabel?: string
): Promise<CodeRepositoryInfo> {
  return sendRepositoryArchive(
    `/domains/${domainId}/repositories/${repositoryId}/replace`,
    file,
    undefined,
    revisionLabel
  );
}

export async function deleteRepository(domainId: string, repositoryId: string): Promise<boolean> {
  const raw = await request<any>(`/domains/${domainId}/repositories/${repositoryId}`, { method: "DELETE" });
  return raw.storage_cleanup_complete;
}

// --- Memory ---

function mapMemory(raw: any): MemoryInfo {
  return {
    id: raw.id,
    content: raw.content,
    conversationId: raw.conversation_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function mapInheritedMemory(raw: any): InheritedMemoryInfo {
  return { ...mapMemory(raw), scopeId: raw.scope_id, scopeName: raw.scope_name };
}

export async function listMemories(domainId: string): Promise<MemoryInfo[]> {
  const raw = await request<any[]>(`/domains/${domainId}/memories`);
  return raw.map(mapMemory);
}

export async function listInheritedMemories(domainId: string): Promise<InheritedMemoryInfo[]> {
  const raw = await request<any[]>(`/domains/${domainId}/memories/inherited`);
  return raw.map(mapInheritedMemory);
}

export async function createMemory(domainId: string, content: string, conversationId?: string | null): Promise<MemoryInfo> {
  const raw = await request<any>(`/domains/${domainId}/memories`, {
    method: "POST",
    body: JSON.stringify({ content, conversation_id: conversationId ?? null }),
  });
  return mapMemory(raw);
}

export async function updateMemory(domainId: string, memoryId: string, content: string): Promise<MemoryInfo> {
  const raw = await request<any>(`/domains/${domainId}/memories/${memoryId}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
  return mapMemory(raw);
}

export async function deleteMemory(domainId: string, memoryId: string): Promise<void> {
  await request(`/domains/${domainId}/memories/${memoryId}`, { method: "DELETE" });
}

// --- Chat streaming ---

export interface StreamHandlers {
  onPrompt?: (layers: PromptLayer[]) => void;
  onToken?: (text: string) => void;
  onDone?: (
    conversationId: string,
    messageId: string,
    citations: Citation[],
    metrics: GenerationMetrics | null
  ) => void;
  onError?: (message: string) => void;
}

async function consumeNdjsonStream(res: Response, handlers: StreamHandlers): Promise<void> {
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    handlers.onError?.(body.detail ?? `Request failed (${res.status})`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "prompt") handlers.onPrompt?.((event.layers ?? []).map(mapPromptLayer));
      else if (event.type === "token") handlers.onToken?.(event.text);
      else if (event.type === "done")
        handlers.onDone?.(
          event.conversation_id,
          event.message_id,
          (event.citations ?? []).map(mapCitation),
          mapGenerationMetrics(event.metrics)
        );
      else if (event.type === "error") handlers.onError?.(event.detail);
    }
  }
}

export async function sendMessageStream(
  domainId: string,
  body: { conversationId: string | null; text: string },
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}/domains/${domainId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ conversation_id: body.conversationId, text: body.text }),
    signal,
  });
  await consumeNdjsonStream(res, handlers);
}

export async function regenerateStream(
  conversationId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}/conversations/${conversationId}/regenerate`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  });
  await consumeNdjsonStream(res, handlers);
}
