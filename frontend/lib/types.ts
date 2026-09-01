export type InheritancePolicy = "private" | "inherited";

export interface ModelInfo {
  tag: string;
  name: string;
  sizeBytes: number;
  parameterSize: string | null;
  quantizationLevel: string | null;
  contextLength: number | null;
  modifiedAt: string | null;
}

export interface ModelProfile {
  id: string;
  tag: string;
  name: string;
  contextLength: number;
  temperature: number;
  topP: number;
  topK: number;
  repeatPenalty: number;
}

export interface DomainModelSettings {
  domainId: string;
  modelTag: string;
  contextLength: number;
  maxOutputTokens: number;
  temperature: number;
  topP: number;
  topK: number;
  repeatPenalty: number;
  source: "domain" | "framework_default";
  nativeContextLength: number | null;
  detectedAllocatedContextLength: number | null;
  recommendedContextLength: number;
  recommendationBasis: string;
}

export interface SubDomain {
  id: string;
  name: string;
  slug: string;
  description: string;
  prompt: string;
  inheritance: InheritancePolicy;
  shareWithSiblings: boolean;
}

export interface Domain {
  id: string;
  name: string;
  slug: string;
  description: string;
  prompt: string;
  inheritance: InheritancePolicy;
  shareWithSiblings: boolean;
  /** Client-only UI state — whether the tree row is expanded. Never persisted. */
  expanded: boolean;
  subdomains: SubDomain[];
}

export interface Citation {
  sourceType: "document" | "repository";
  documentId: string | null;
  documentName: string | null;
  scopeId: string;
  scopeName: string;
  heading: string | null;
  pageNumber: number | null;
  chunkIndex: number;
  repositoryId: string | null;
  repositoryName: string | null;
  revisionLabel: string | null;
  snapshotHash: string | null;
  relativePath: string | null;
  startLine: number | null;
  endLine: number | null;
}

export type GenerationStatus = "completed" | "truncated" | "empty_fallback" | "error_fallback" | "stopped" | "client_error";

export interface GenerationMetrics {
  promptTokens: number | null;
  outputTokens: number | null;
  tokensPerSecond: number | null;
  timeToFirstTokenMs: number | null;
  promptEvalDurationMs: number | null;
  generationDurationMs: number | null;
  loadDurationMs: number | null;
  totalDurationMs: number | null;
  finishReason: string | null;
  status: GenerationStatus;
}

export type LearningCardCategory = "key_idea" | "action" | "caution" | "example";

export interface LearningCard {
  category: LearningCardCategory;
  title: string;
  takeaway: string;
}

export interface LearningCardSet {
  sourceMessageId: string;
  modelTag: string;
  createdAt: string;
  title: string;
  summary: string;
  cards: LearningCard[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
  generationMetrics: GenerationMetrics | null;
  learningCards: LearningCardSet | null;
}

export type DocumentStatus = "pending" | "ready" | "failed";

export interface DocumentInfo {
  id: string;
  filename: string;
  sourceType: string;
  folderPath: string;
  tags: string[];
  version: number;
  status: DocumentStatus;
  error: string | null;
  chunkCount: number;
  createdAt: string;
  markdownAvailable: boolean;
  markdownFilename: string | null;
}

export interface InheritedDocumentInfo extends DocumentInfo {
  scopeId: string;
  scopeName: string;
}

export interface DocumentPreview {
  filename: string;
  sourceType: string;
  format: "markdown" | "text";
  content: string;
  characterCount: number;
  truncated: boolean;
  markdownCopy: boolean;
}

export interface DocumentOrganizationSuggestion {
  documentId: string;
  filename: string;
  folderPath: string;
  tags: string[];
  reason: string;
}

export interface DocumentOrganizationPreview {
  modelTag: string;
  documentSetHash: string;
  suggestions: DocumentOrganizationSuggestion[];
  warnings: string[];
}

export type RepositoryStatus = "validating" | "indexing" | "ready" | "failed" | "deleting";

export interface RepositoryExclusion {
  path: string;
  reason: string;
  security: boolean;
}

export interface CodeRepositoryInfo {
  id: string;
  scopeId: string;
  name: string;
  archiveFilename: string;
  revisionLabel: string | null;
  contentHash: string;
  status: RepositoryStatus;
  error: string | null;
  fileCount: number;
  skippedFileCount: number;
  securityExcludedCount: number;
  chunkCount: number;
  exclusions: RepositoryExclusion[];
  createdAt: string;
  updatedAt: string;
}

export interface MemoryInfo {
  id: string;
  content: string;
  conversationId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface InheritedMemoryInfo extends MemoryInfo {
  scopeId: string;
  scopeName: string;
}

export interface Conversation {
  id: string;
  title: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

export interface PromptLayer {
  key: string;
  name: string;
  category: "rules" | "scope" | "knowledge" | "conversation";
  content: string;
  applied: boolean;
  state: "included" | "not_included" | "planned";
  reason: string;
  sourceType: string;
  sourceName: string | null;
  editTarget: "scope_settings" | "parent_scope" | "memory" | "documents" | "repositories" | null;
  modelRole: "system" | "conversation" | "user" | null;
  control: "standard" | "advanced" | "fixed" | "planned";
  ownerEnabled: boolean | null;
}

export type PromptPreviewStatus = "idle" | "updating" | "up_to_date" | "stale" | "unavailable";
export type PromptPreviewSource = "draft" | "sent";

export type OptimizerAvailability = "available" | "partial" | "unavailable" | "unsupported";

export interface OptimizerWarning {
  code: string;
  severity: "info" | "warning" | "error";
  title: string;
  detail: string;
  action: string | null;
}

export interface OptimizerAccelerator {
  vendor: "apple" | "nvidia" | "amd" | "unknown";
  name: string;
  computeBackend: string | null;
  memoryKind: "dedicated" | "unified" | "shared" | "unknown";
  memoryTotalBytes: number | null;
  memoryUsedBytes: number | null;
  utilizationPercent: number | null;
  powerWatts: number | null;
  temperatureCelsius: number | null;
  driverVersion: string | null;
  source: string;
}

export interface OptimizerReport {
  schemaVersion: string;
  capturedAt: string;
  readOnly: true;
  requestedModelTag: string | null;
  runtimeHost: {
    source: "framework_runtime";
    runtimeKind: "native" | "container";
    appliesToOllamaDevice: "yes" | "no" | "partial" | "unknown";
    osName: string;
    osRelease: string;
    cpu: {
      model: string | null;
      architecture: string;
      logicalCores: number | null;
      physicalCores: number | null;
    };
    memory: {
      totalBytes: number | null;
      availableBytes: number | null;
      swapTotalBytes: number | null;
      swapUsedBytes: number | null;
    };
    storage: {
      observedPath: string;
      totalBytes: number | null;
      availableBytes: number | null;
    };
    accelerators: OptimizerAccelerator[];
  };
  ollama: {
    endpoint: string;
    relationship: "same_runtime" | "container_service" | "native_host" | "remote" | "unknown";
    hardwareVisibility: "full" | "partial" | "unknown";
    reachable: boolean;
    version: string | null;
    installedModelCount: number | null;
    error: { code: string; message: string; action: string } | null;
  };
  selectedModel: {
    tag: string;
    name: string;
    digest: string | null;
    sizeBytes: number | null;
    parameterSize: string | null;
    quantizationLevel: string | null;
    family: string | null;
    capabilities: string[];
    nativeContextLength: number | null;
    loaded: boolean;
    loadedSizeBytes: number | null;
    acceleratorSizeBytes: number | null;
    acceleratorFraction: number | null;
    allocatedContextLength: number | null;
    placement: "cpu" | "accelerator" | "split" | "unknown";
    expiresAt: string | null;
  } | null;
  capabilities: {
    key: string;
    label: string;
    status: OptimizerAvailability;
    detail: string;
    source: string;
  }[];
  warnings: OptimizerWarning[];
}

export type OptimizerRunState =
  | "planned"
  | "queued"
  | "detecting"
  | "warming"
  | "measuring"
  | "evaluating"
  | "completed"
  | "cancelled"
  | "failed";
export type OptimizerObjective = "balanced" | "fast_response" | "large_context" | "low_memory" | "low_energy";
export type OptimizerMode = "quick" | "standard";
export type OptimizerBenchmarkKind = "baseline" | "context_comparison";

export interface OptimizerPlacement {
  kind: "cpu" | "accelerator" | "split" | "unknown";
  acceleratorFraction: number | null;
  loadedSizeBytes: number | null;
  acceleratorSizeBytes: number | null;
  source: string;
}

export interface OptimizerMeasurement {
  id: string;
  trialIndex: number;
  workloadCase: string;
  isWarmup: boolean;
  coldLoad: boolean | null;
  state: string;
  ttftMs: number | null;
  promptTokens: number | null;
  generatedTokens: number | null;
  promptTokensPerSecond: number | null;
  generationTokensPerSecond: number | null;
  loadDurationMs: number | null;
  totalDurationMs: number | null;
  wallDurationMs: number | null;
  outputCharacters: number;
  finishReason: string | null;
  placement: OptimizerPlacement | null;
  resourceSnapshot: Record<string, unknown> | null;
  errorCode: string | null;
  errorMessage: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface OptimizerRun {
  schemaVersion: string;
  id: string;
  modelTag: string;
  benchmarkKind: OptimizerBenchmarkKind;
  objective: OptimizerObjective;
  mode: OptimizerMode;
  workloadVersion: string;
  runnerVersion: string;
  endpointDisplay: string;
  state: OptimizerRunState;
  currentStageDetail: string | null;
  totalTrials: number;
  completedTrials: number;
  cancelRequested: boolean;
  ollamaVersion: string | null;
  hardwareSnapshot: OptimizerReport | null;
  summary: {
    measured_trials?: number;
    warmup_trials?: number;
    failed_trials?: number;
    medians?: {
      ttft_ms: number | null;
      prompt_tokens_per_second: number | null;
      generation_tokens_per_second: number | null;
      total_duration_ms: number | null;
      generated_tokens: number | null;
    };
    latest_placement?: OptimizerPlacement | null;
    generated_text_retained?: boolean;
    settings_changed?: boolean;
    recommendation_evaluated_at?: string;
    recommendation?: {
      score_version: string;
      setting_scope: "model_profile";
      objective: OptimizerObjective;
      weights: Record<string, number>;
      workload_context_need: number;
      candidate_results: {
        candidate_id: string;
        label: string;
        context_length: number;
        is_current: boolean;
        state: string;
        measured_trials: number;
        expected_measured_trials: number;
        reliability: number;
        medians: {
          ttft_ms: number | null;
          generation_tokens_per_second: number | null;
          prompt_tokens_per_second: number | null;
          total_duration_ms: number | null;
          generated_tokens: number | null;
          power_watts: number | null;
          tokens_per_joule: number | null;
        };
        variance: {
          generation_rate_cv: number | null;
          ttft_cv: number | null;
          power_cv: number | null;
          method?: "maximum_within_workload_cv";
          by_workload?: Record<string, {
            generation_rate_cv: number | null;
            ttft_cv: number | null;
            power_cv: number | null;
          }>;
        };
        minimum_repetitions_per_workload?: number;
        placement: OptimizerPlacement | null;
        loaded_size_bytes: number | null;
        error_code: string | null;
        error_message: string | null;
        stop_reason: string | null;
        score: number | null;
        dimensions: Record<string, number> | null;
      }[];
      pareto_candidate_ids: string[];
      baseline_candidate_id: string | null;
      winner_candidate_id: string | null;
      winning_context_length: number | null;
      deltas_from_current: {
        context_tokens: number;
        generation_rate_percent: number | null;
        ttft_percent: number | null;
        loaded_size_bytes: number | null;
      } | null;
      failed_candidate_ids: string[];
      confidence: "high" | "medium" | "low" | "unavailable";
      confidence_reasons: string[];
      keep_current_settings: {
        candidate_id: string | null;
        context_length: number | null;
        available: boolean;
      };
      plain_language: string;
    };
  };
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  estimatedSeconds: number;
  disruptionNotice: string;
  candidates: {
    id: string;
    label: string;
    settings: {
      num_ctx?: number;
      num_predict?: number;
      temperature?: number;
      seed?: number;
      is_current?: boolean;
      stop_reason?: string;
    };
    state: string;
    measurements: OptimizerMeasurement[];
  }[];
}

export interface OptimizerApplyIssue {
  code: string;
  title: string;
  detail: string;
  action: string | null;
}

export interface OptimizerContextApplyPreview {
  schemaVersion: string;
  previewVersion: string;
  runId: string;
  status: "ready" | "blocked" | "no_change";
  canApply: boolean;
  settingScope: "model_profile";
  modelTag: string;
  profileId: string | null;
  profileActive: boolean;
  currentContextLength: number | null;
  recommendedContextLength: number | null;
  targetContextLength: number | null;
  selectionKind: "recommended" | "measured_candidate" | "custom" | "unavailable";
  deltaTokens: number | null;
  nativeContextLimit: number | null;
  safetyCeiling: number;
  effectTiming: "next_model_request";
  restartRequired: false;
  affectedScope: string;
  blockingReasons: OptimizerApplyIssue[];
  warnings: OptimizerApplyIssue[];
  checkedAt: string;
  evidence: {
    scoreVersion: string | null;
    runnerVersion: string;
    runCompletedAt: string | null;
    measuredTrials: number;
    confidence: string;
    endpointStatus: "match" | "changed";
    modelDigestStatus: "match" | "changed" | "unavailable";
    ollamaVersionStatus: "match" | "changed" | "unavailable";
    hardwareStatus: "match" | "changed" | "partial" | "unavailable";
    hardwareVisibility: "full" | "partial" | "unknown";
  };
}

export interface OptimizerContextAudit {
  id: string;
  runId: string | null;
  sourceAuditId: string | null;
  modelTag: string;
  action: "apply" | "rollback";
  previousContextLength: number;
  newContextLength: number;
  effectiveContextLength: number;
  previewVersion: string;
  scoreVersion: string | null;
  runnerVersion: string;
  acknowledgedWarningCodes: string[];
  rollbackAvailable: boolean;
  createdAt: string;
}

export interface OptimizerContextChangeResult {
  schemaVersion: string;
  verified: true;
  profileActive: boolean;
  effectiveContextLength: number;
  effectTiming: "next_model_request";
  restartRequired: false;
  audit: OptimizerContextAudit;
}

export type RightMode = "inspector" | "documents" | "memory" | "optimizer" | "settings";

export interface ToastItem {
  id: string;
  message: string;
}

/** A domain or sub-domain, whichever is currently active. */
export type ActiveScope = Domain | SubDomain;
