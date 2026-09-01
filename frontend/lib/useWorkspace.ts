"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";
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
  MemoryInfo,
  ModelInfo,
  ModelProfile,
  OptimizerContextApplyPreview,
  OptimizerContextAudit,
  OptimizerReport,
  OptimizerMode,
  OptimizerObjective,
  OptimizerRun,
  PromptLayer,
  PromptPreviewSource,
  PromptPreviewStatus,
  RightMode,
  SubDomain,
  ToastItem,
} from "./types";

interface WorkspaceState {
  loading: boolean;
  modelsUnreachable: boolean;
  models: ModelInfo[];
  activeModelTag: string | null;
  activeModelProfile: ModelProfile | null;
  domainModelSettings: DomainModelSettings | null;
  domains: Domain[];
  activeDomainId: string | null;
  activeSubdomainId: string | null;
  conversations: Conversation[];
  activeConv: ConversationDetail | null;
  activeConvId: string | null;
  promptLayers: PromptLayer[];
  promptPreviewStatus: PromptPreviewStatus;
  promptPreviewSource: PromptPreviewSource;
  promptPreviewDraft: string;
  promptPreviewError: string | null;
  rightMode: RightMode;
  streaming: boolean;
  learningCardsLoading: boolean;
  generationPhase: "idle" | "preparing_context" | "waiting_for_model" | "generating";
  generationStartedAt: number | null;
  generationFirstTokenAt: number | null;
  generationCharacters: number;
  generationChunks: number;
  documents: DocumentInfo[];
  inheritedDocuments: InheritedDocumentInfo[];
  documentsLoading: boolean;
  repositories: CodeRepositoryInfo[];
  repositoriesLoading: boolean;
  memories: MemoryInfo[];
  inheritedMemories: InheritedMemoryInfo[];
  memoriesLoading: boolean;
  optimizerReport: OptimizerReport | null;
  optimizerLoading: boolean;
  optimizerError: string | null;
  optimizerRuns: OptimizerRun[];
  optimizerRunsLoading: boolean;
  optimizerApplyPreview: OptimizerContextApplyPreview | null;
  optimizerApplyPreviewLoading: boolean;
  optimizerContextAudits: OptimizerContextAudit[];
  optimizerContextChangeLoading: boolean;
}

function initialState(): WorkspaceState {
  return {
    loading: true,
    modelsUnreachable: false,
    models: [],
    activeModelTag: null,
    activeModelProfile: null,
    domainModelSettings: null,
    domains: [],
    activeDomainId: null,
    activeSubdomainId: null,
    conversations: [],
    activeConv: null,
    activeConvId: null,
    promptLayers: [],
    promptPreviewStatus: "idle",
    promptPreviewSource: "draft",
    promptPreviewDraft: "",
    promptPreviewError: null,
    rightMode: "inspector",
    streaming: false,
    learningCardsLoading: false,
    generationPhase: "idle",
    generationStartedAt: null,
    generationFirstTokenAt: null,
    generationCharacters: 0,
    generationChunks: 0,
    documents: [],
    inheritedDocuments: [],
    documentsLoading: false,
    repositories: [],
    repositoriesLoading: false,
    memories: [],
    inheritedMemories: [],
    memoriesLoading: false,
    optimizerReport: null,
    optimizerLoading: false,
    optimizerError: null,
    optimizerRuns: [],
    optimizerRunsLoading: false,
    optimizerApplyPreview: null,
    optimizerApplyPreviewLoading: false,
    optimizerContextAudits: [],
    optimizerContextChangeLoading: false,
  };
}

function findDomain(domains: Domain[], id: string | null): Domain | null {
  return domains.find((d) => d.id === id) ?? null;
}

function findSubdomain(domain: Domain | null, id: string | null): SubDomain | null {
  if (!domain || !id) return null;
  return domain.subdomains.find((s) => s.id === id) ?? null;
}

function mapDomains(domains: Domain[], scopeId: string, patch: Partial<SubDomain>): Domain[] {
  return domains.map((d) => {
    if (d.id === scopeId) return { ...d, ...patch };
    if (d.subdomains.some((s) => s.id === scopeId)) {
      return { ...d, subdomains: d.subdomains.map((s) => (s.id === scopeId ? { ...s, ...patch } : s)) };
    }
    return d;
  });
}

export function useWorkspace() {
  const [state, setState] = useState<WorkspaceState>(initialState);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const previewAbortRef = useRef<AbortController | null>(null);
  const previewSequenceRef = useRef(0);

  const activeDomain = findDomain(state.domains, state.activeDomainId);
  const activeSubdomain = findSubdomain(activeDomain, state.activeSubdomainId);
  const activeScope = activeSubdomain ?? activeDomain;
  const activeModel = state.models.find((m) => m.tag === state.activeModelTag) ?? null;
  const scopePath = activeDomain
    ? `/${activeDomain.slug}${activeSubdomain ? `/${activeSubdomain.slug}` : ""}`
    : "";

  useEffect(() => {
    return () => previewAbortRef.current?.abort();
  }, []);

  const pushToast = useCallback((message: string) => {
    const id = `t${Date.now()}${Math.random().toString(36).slice(2)}`;
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 2600);
  }, []);

  const reportError = useCallback(
    (err: unknown, fallback: string) => {
      pushToast(err instanceof api.ApiError ? err.message : fallback);
    },
    [pushToast]
  );

  const loadDocuments = useCallback(
    async (scopeId: string) => {
      setState((prev) => ({ ...prev, documentsLoading: true }));
      try {
        const [documents, inheritedDocuments] = await Promise.all([
          api.listDocuments(scopeId),
          api.listInheritedDocuments(scopeId),
        ]);
        setState((prev) => ({ ...prev, documents, inheritedDocuments, documentsLoading: false }));
      } catch (err) {
        setState((prev) => ({ ...prev, documentsLoading: false }));
        reportError(err, "Could not load documents for this scope.");
      }
    },
    [reportError]
  );

  const loadMemories = useCallback(
    async (scopeId: string) => {
      setState((prev) => ({ ...prev, memoriesLoading: true }));
      try {
        const [memories, inheritedMemories] = await Promise.all([
          api.listMemories(scopeId),
          api.listInheritedMemories(scopeId),
        ]);
        setState((prev) => ({ ...prev, memories, inheritedMemories, memoriesLoading: false }));
      } catch (err) {
        setState((prev) => ({ ...prev, memoriesLoading: false }));
        reportError(err, "Could not load memories for this scope.");
      }
    },
    [reportError]
  );

  const loadRepositories = useCallback(
    async (scopeId: string) => {
      setState((prev) => ({ ...prev, repositoriesLoading: true }));
      try {
        const repositories = await api.listRepositories(scopeId);
        setState((prev) => ({ ...prev, repositories, repositoriesLoading: false }));
      } catch (err) {
        setState((prev) => ({ ...prev, repositoriesLoading: false }));
        reportError(err, "Could not load repositories for this scope.");
      }
    },
    [reportError]
  );

  const selectScope = useCallback(
    async (domainId: string, subId: string | null) => {
      previewAbortRef.current?.abort();
      previewSequenceRef.current += 1;
      setState((prev) => ({
        ...prev,
        domains: prev.domains.map((domain) => ({
          ...domain,
          expanded: domain.id === domainId,
        })),
        activeDomainId: domainId,
        activeSubdomainId: subId,
        conversations: [],
        activeConv: null,
        activeConvId: null,
        promptLayers: [],
        promptPreviewStatus: "idle",
        promptPreviewSource: "draft",
        promptPreviewDraft: "",
        promptPreviewError: null,
        streaming: false,
        learningCardsLoading: false,
        generationPhase: "idle",
        generationStartedAt: null,
        generationFirstTokenAt: null,
        generationCharacters: 0,
        generationChunks: 0,
        documents: [],
        inheritedDocuments: [],
        repositories: [],
        memories: [],
        inheritedMemories: [],
        domainModelSettings: null,
      }));
      const scopeId = subId ?? domainId;
      loadDocuments(scopeId);
      loadRepositories(scopeId);
      loadMemories(scopeId);
      api.getDomainModelSettings(scopeId).then((settings) => {
        setState((prev) => prev.activeDomainId === domainId && prev.activeSubdomainId === subId
          ? { ...prev, domainModelSettings: settings, activeModelTag: settings.modelTag }
          : prev);
      }).catch((err) => reportError(err, "Could not load model settings for this domain."));
      try {
        const convs = await api.listConversations(scopeId);
        let detail: ConversationDetail | null = null;
        const last = convs[convs.length - 1];
        if (last) {
          detail = await api.getConversation(last.id);
        }
        setState((prev) => ({
          ...prev,
          conversations: convs,
          activeConv: detail,
          activeConvId: detail?.id ?? null,
        }));
      } catch (err) {
        reportError(err, "Could not load conversations for this scope.");
      }
    },
    [reportError, loadDocuments, loadRepositories, loadMemories]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [modelsResult, profileResult, domainsResult] = await Promise.allSettled([
        api.listInstalledModels(),
        api.getActiveModelProfile(),
        api.listDomains(),
      ]);
      if (cancelled) return;

      const models = modelsResult.status === "fulfilled" ? modelsResult.value : [];
      const modelsUnreachable = modelsResult.status === "rejected";
      const activeModelProfile = profileResult.status === "fulfilled" ? profileResult.value : null;
      const activeModelTag = activeModelProfile?.tag ?? null;
      const domains = domainsResult.status === "fulfilled" ? domainsResult.value : [];

      if (modelsResult.status === "rejected") reportError(modelsResult.reason, "Could not reach Ollama.");
      if (domainsResult.status === "rejected") reportError(domainsResult.reason, "Could not load domains.");

      setState((prev) => ({ ...prev, models, modelsUnreachable, activeModelTag, activeModelProfile, domains, loading: false }));
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectConversation = useCallback(
    async (convId: string) => {
      previewAbortRef.current?.abort();
      previewSequenceRef.current += 1;
      setState((prev) => ({
        ...prev,
        activeConvId: convId,
        activeConv: null,
        promptLayers: [],
        promptPreviewStatus: "idle",
        promptPreviewSource: "draft",
        promptPreviewDraft: "",
        promptPreviewError: null,
        streaming: false,
        learningCardsLoading: false,
        generationPhase: "idle",
        generationStartedAt: null,
        generationFirstTokenAt: null,
        generationCharacters: 0,
        generationChunks: 0,
      }));
      try {
        const detail = await api.getConversation(convId);
        setState((prev) =>
          prev.activeConvId === convId ? { ...prev, activeConv: detail, activeConvId: detail.id } : prev
        );
      } catch (err) {
        reportError(err, "Could not load that conversation.");
      }
    },
    [reportError]
  );

  const newConversation = useCallback(() => {
    previewAbortRef.current?.abort();
    previewSequenceRef.current += 1;
    setState((prev) => ({
      ...prev,
      activeConv: null,
      activeConvId: null,
      promptLayers: [],
      promptPreviewStatus: "idle",
      promptPreviewSource: "draft",
      promptPreviewDraft: "",
      promptPreviewError: null,
      streaming: false,
      learningCardsLoading: false,
      generationPhase: "idle",
      generationStartedAt: null,
      generationFirstTokenAt: null,
      generationCharacters: 0,
      generationChunks: 0,
    }));
  }, []);

  const setRightMode = useCallback((mode: RightMode) => {
    setState((prev) => ({ ...prev, rightMode: mode }));
  }, []);

  const switchModel = useCallback(
    async (tag: string) => {
      try {
        const scopeId = state.activeSubdomainId ?? state.activeDomainId;
        if (scopeId && state.domainModelSettings) {
          const current = state.domainModelSettings;
          const saved = await api.updateDomainModelSettings(scopeId, {
            modelTag: tag,
            contextLength: current.contextLength,
            maxOutputTokens: current.maxOutputTokens,
            temperature: current.temperature,
            topP: current.topP,
            topK: current.topK,
            repeatPenalty: current.repeatPenalty,
          });
          setState((prev) => ({ ...prev, activeModelTag: tag, domainModelSettings: saved }));
          pushToast(`Model saved for this domain. Request context: ${saved.contextLength.toLocaleString()} tokens.`);
        } else {
          const profile = await api.setActiveModelProfile(tag);
          setState((prev) => ({ ...prev, activeModelTag: profile.tag, activeModelProfile: profile }));
          pushToast(`Framework default model switched. Context: ${profile.contextLength.toLocaleString()} tokens.`);
        }
      } catch (err) {
        reportError(err, "Could not switch model.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, state.domainModelSettings, pushToast, reportError]
  );

  const saveDomainModelSettings = useCallback(async (settings: DomainModelSettings) => {
    const scopeId = state.activeSubdomainId ?? state.activeDomainId;
    if (!scopeId) return false;
    try {
      const saved = await api.updateDomainModelSettings(scopeId, settings);
      setState((prev) => ({ ...prev, domainModelSettings: saved, activeModelTag: saved.modelTag }));
      pushToast("Model settings saved for this domain.");
      return true;
    } catch (err) {
      reportError(err, "Could not save model settings.");
      return false;
    }
  }, [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]);

  const previewPrompt = useCallback(
    async (draft: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      const sequence = previewSequenceRef.current + 1;
      previewSequenceRef.current = sequence;
      previewAbortRef.current?.abort();
      const controller = new AbortController();
      previewAbortRef.current = controller;
      setState((prev) => ({
        ...prev,
        promptPreviewStatus: "updating",
        promptPreviewSource: "draft",
        promptPreviewDraft: draft,
        promptPreviewError: null,
      }));
      try {
        const layers = await api.promptPreview(scopeId, draft, state.activeConv?.id ?? null, controller.signal);
        if (previewSequenceRef.current !== sequence) return;
        setState((prev) => ({
          ...prev,
          promptLayers: layers,
          promptPreviewStatus: "up_to_date",
          promptPreviewSource: "draft",
          promptPreviewDraft: draft,
          promptPreviewError: null,
        }));
      } catch (err) {
        if (controller.signal.aborted || previewSequenceRef.current !== sequence) return;
        const message = err instanceof api.ApiError ? err.message : "The preview could not be updated.";
        setState((prev) => ({
          ...prev,
          promptPreviewStatus: prev.promptLayers.length ? "stale" : "unavailable",
          promptPreviewSource: "draft",
          promptPreviewDraft: draft,
          promptPreviewError: message,
        }));
      }
    },
    [state.activeDomainId, state.activeSubdomainId, state.activeConv]
  );

  const setPromptLayerEnabled = useCallback(
    async (layerKey: string, enabled: boolean, riskAcknowledged: boolean, previewDraft: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId || state.streaming) return false;
      try {
        await api.updatePromptLayerControl(scopeId, layerKey, enabled, riskAcknowledged);
        pushToast(`${enabled ? "Enabled" : "Disabled"} this prompt layer for the selected scope.`);
        await previewPrompt(previewDraft);
        return true;
      } catch (err) {
        reportError(err, "Could not change the prompt layer setting.");
        return false;
      }
    },
    [state.activeDomainId, state.activeSubdomainId, state.streaming, previewPrompt, pushToast, reportError]
  );

  function appendAssistantChunk(chunk: string) {
    const receivedAt = Date.now();
    setState((prev) => {
      if (!prev.activeConv) return prev;
      const messages = [...prev.activeConv.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, text: last.text + chunk };
      } else {
        messages.push({
          id: "pending",
          role: "assistant",
          text: chunk,
          citations: [],
          generationMetrics: null,
          learningCards: null,
        });
      }
      return {
        ...prev,
        generationPhase: "generating",
        generationFirstTokenAt: prev.generationFirstTokenAt ?? receivedAt,
        generationCharacters: prev.generationCharacters + chunk.length,
        generationChunks: prev.generationChunks + 1,
        activeConv: { ...prev.activeConv, messages },
      };
    });
  }

  function emptyMetrics(status: GenerationMetrics["status"]): GenerationMetrics {
    return {
      promptTokens: null,
      outputTokens: null,
      tokensPerSecond: null,
      timeToFirstTokenMs: null,
      promptEvalDurationMs: null,
      generationDurationMs: null,
      loadDurationMs: null,
      totalDurationMs: null,
      finishReason: null,
      status,
    };
  }

  function finalizeAssistant(messageId: string, citations: Citation[], metrics: GenerationMetrics | null) {
    setState((prev) => {
      if (!prev.activeConv) return prev;
      const messages = [...prev.activeConv.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, id: messageId, citations, generationMetrics: metrics };
      } else {
        messages.push({
          id: messageId,
          role: "assistant",
          text: "I couldn't produce a reliable answer. Could you rephrase the request and tell me the specific outcome you need?",
          citations,
          generationMetrics: metrics ?? emptyMetrics("empty_fallback"),
          learningCards: null,
        });
      }
      return {
        ...prev,
        streaming: false,
        generationPhase: "idle",
        generationStartedAt: null,
        generationFirstTokenAt: null,
        generationCharacters: 0,
        generationChunks: 0,
        activeConv: { ...prev.activeConv, messages },
      };
    });
  }

  function showClientGenerationFailure(serverMessage?: string) {
    setState((prev) => {
      if (!prev.activeConv) return { ...prev, streaming: false, generationPhase: "idle" };
      const messages = [...prev.activeConv.messages];
      const last = messages[messages.length - 1];
      const text = serverMessage ??
        "I couldn't receive a complete response from the local model. Please check that the backend and Ollama are reachable, then retry your prompt.";
      if (last?.role === "assistant") {
        messages[messages.length - 1] = {
          ...last,
          text: last.text.trim() ? `${last.text}\n\n[The response was interrupted and may be incomplete.]` : text,
          generationMetrics: emptyMetrics("client_error"),
        };
      } else {
        messages.push({
          id: `local-error-${Date.now()}`,
          role: "assistant",
          text,
          citations: [],
          generationMetrics: emptyMetrics("client_error"),
          learningCards: null,
        });
      }
      return {
        ...prev,
        streaming: false,
        generationPhase: "idle",
        generationStartedAt: null,
        generationFirstTokenAt: null,
        generationCharacters: 0,
        generationChunks: 0,
        activeConv: { ...prev.activeConv, messages },
      };
    });
  }

  const sendMessage = useCallback(
    (rawText: string) => {
      const text = rawText.trim();
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!text || state.streaming || !scopeId) return;
      if (!state.activeModelTag) {
        pushToast("Select a model before sending a message.");
        return;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      const conversationIdAtSend = state.activeConv?.id ?? null;
      previewAbortRef.current?.abort();
      previewSequenceRef.current += 1;

      setState((prev) => {
        const base: ConversationDetail = prev.activeConv ?? { id: "", title: text.slice(0, 34), messages: [] };
        const userMsg: ChatMessage = {
          id: `u${Date.now()}`,
          role: "user",
          text,
          citations: [],
          generationMetrics: null,
          learningCards: null,
        };
        return {
          ...prev,
          streaming: true,
          generationPhase: "preparing_context",
          generationStartedAt: Date.now(),
          generationFirstTokenAt: null,
          generationCharacters: 0,
          generationChunks: 0,
          promptPreviewStatus: "updating",
          promptPreviewSource: "sent",
          promptPreviewDraft: text,
          promptPreviewError: null,
          activeConv: { ...base, messages: [...base.messages, userMsg] },
        };
      });

      api
        .sendMessageStream(
          scopeId,
          { conversationId: conversationIdAtSend, text },
          {
            onPrompt: (layers) => setState((prev) => ({
              ...prev,
              promptLayers: layers,
              promptPreviewStatus: "up_to_date",
              promptPreviewSource: "sent",
              promptPreviewDraft: text,
              promptPreviewError: null,
              generationPhase: prev.generationFirstTokenAt ? "generating" : "waiting_for_model",
            })),
            onToken: appendAssistantChunk,
            onDone: async (conversationId, messageId, citations, metrics) => {
              finalizeAssistant(messageId, citations, metrics);
              setState((prev) => ({
                ...prev,
                activeConvId: conversationId,
                activeConv: prev.activeConv ? { ...prev.activeConv, id: conversationId } : prev.activeConv,
              }));
              try {
                const convs = await api.listConversations(scopeId);
                setState((prev) => ({ ...prev, conversations: convs }));
              } catch {
                // non-critical
              }
            },
            onError: (msg) => {
              pushToast(msg);
              showClientGenerationFailure(msg);
              setState((prev) => ({
                ...prev,
                promptPreviewStatus:
                  prev.promptPreviewStatus === "up_to_date"
                    ? "up_to_date"
                    : prev.promptLayers.length
                      ? "stale"
                      : "unavailable",
                promptPreviewError: prev.promptPreviewStatus === "up_to_date" ? null : msg,
              }));
            },
          },
          controller.signal
        )
        .catch(() => {
          if (controller.signal.aborted) return;
          showClientGenerationFailure();
          setState((prev) => ({
            ...prev,
            promptPreviewStatus:
              prev.promptPreviewStatus === "up_to_date"
                ? "up_to_date"
                : prev.promptLayers.length
                  ? "stale"
                  : "unavailable",
            promptPreviewError:
              prev.promptPreviewStatus === "up_to_date" ? null : "The sent prompt snapshot is unavailable.",
          }));
        });
    },
    [state.activeDomainId, state.activeSubdomainId, state.activeModelTag, state.activeConv, state.streaming, pushToast]
  );

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => {
      if (!prev.activeConv) return { ...prev, streaming: false, generationPhase: "idle" };
      const messages = [...prev.activeConv.messages];
      const last = messages[messages.length - 1];
      if (last?.role === "assistant") {
        messages[messages.length - 1] = { ...last, generationMetrics: emptyMetrics("stopped") };
      } else {
        messages.push({
          id: `stopped-${Date.now()}`,
          role: "assistant",
          text: "Generation was stopped before an answer was produced.",
          citations: [],
          generationMetrics: emptyMetrics("stopped"),
          learningCards: null,
        });
      }
      return {
        ...prev,
        streaming: false,
        generationPhase: "idle",
        generationStartedAt: null,
        generationFirstTokenAt: null,
        generationCharacters: 0,
        generationChunks: 0,
        promptPreviewStatus:
          prev.promptPreviewStatus === "up_to_date"
            ? "up_to_date"
            : prev.promptLayers.length
              ? "stale"
              : "unavailable",
        promptPreviewError:
          prev.promptPreviewStatus === "up_to_date" ? null : "Generation stopped before the prompt snapshot arrived.",
        activeConv: { ...prev.activeConv, messages },
      };
    });
    pushToast("Generation stopped.");
  }, [pushToast]);

  const regenerate = useCallback(() => {
    const conv = state.activeConv;
    if (!conv || state.streaming || !conv.messages.length) return;
    const lastUserText = [...conv.messages].reverse().find((message) => message.role === "user")?.text ?? "";

    const controller = new AbortController();
    abortRef.current = controller;
    previewAbortRef.current?.abort();
    previewSequenceRef.current += 1;

    setState((prev) => {
      if (!prev.activeConv) return prev;
      const messages = [...prev.activeConv.messages];
      if (messages[messages.length - 1]?.role === "assistant") messages.pop();
      return {
        ...prev,
        streaming: true,
        generationPhase: "preparing_context",
        generationStartedAt: Date.now(),
        generationFirstTokenAt: null,
        generationCharacters: 0,
        generationChunks: 0,
        promptPreviewStatus: "updating",
        promptPreviewSource: "sent",
        promptPreviewDraft: lastUserText,
        promptPreviewError: null,
        activeConv: { ...prev.activeConv, messages },
      };
    });

    api
      .regenerateStream(
        conv.id,
        {
          onPrompt: (layers) => setState((prev) => ({
            ...prev,
            promptLayers: layers,
            promptPreviewStatus: "up_to_date",
            promptPreviewSource: "sent",
            promptPreviewDraft: lastUserText,
            promptPreviewError: null,
            generationPhase: prev.generationFirstTokenAt ? "generating" : "waiting_for_model",
          })),
          onToken: appendAssistantChunk,
          onDone: (_conversationId, messageId, citations, metrics) => {
            finalizeAssistant(messageId, citations, metrics);
          },
          onError: (msg) => {
            pushToast(msg);
            showClientGenerationFailure();
            setState((prev) => ({
              ...prev,
              promptPreviewStatus:
                prev.promptPreviewStatus === "up_to_date"
                  ? "up_to_date"
                  : prev.promptLayers.length
                    ? "stale"
                    : "unavailable",
              promptPreviewError: prev.promptPreviewStatus === "up_to_date" ? null : msg,
            }));
          },
        },
        controller.signal
      )
      .catch(() => {
        if (controller.signal.aborted) return;
        showClientGenerationFailure();
        setState((prev) => ({
          ...prev,
          promptPreviewStatus:
            prev.promptPreviewStatus === "up_to_date"
              ? "up_to_date"
              : prev.promptLayers.length
                ? "stale"
                : "unavailable",
          promptPreviewError:
            prev.promptPreviewStatus === "up_to_date" ? null : "The regenerated prompt snapshot is unavailable.",
        }));
      });
  }, [state.activeConv, state.streaming, pushToast]);

  const createLearningCards = useCallback(async () => {
    const conv = state.activeConv;
    if (!conv || state.streaming || state.learningCardsLoading) return null;
    const source = [...conv.messages].reverse().find((message) => message.role === "assistant");
    if (!source || source.id === "pending" || source.id.startsWith("local-error-") || source.id.startsWith("stopped-")) {
      pushToast("Wait for a completed assistant response before making learning cards.");
      return null;
    }
    if (!state.activeModelTag) {
      pushToast("Select a model before making learning cards.");
      return null;
    }

    setState((prev) => ({ ...prev, learningCardsLoading: true }));
    try {
      const learningCards = await api.createLearningCards(conv.id);
      setState((prev) => {
        if (prev.activeConv?.id !== conv.id) return { ...prev, learningCardsLoading: false };
        return {
          ...prev,
          learningCardsLoading: false,
          activeConv: {
            ...prev.activeConv,
            messages: prev.activeConv.messages.map((message) =>
              message.id === learningCards.sourceMessageId ? { ...message, learningCards } : message
            ),
          },
        };
      });
      pushToast("Learning cards created from the latest response.");
      return learningCards;
    } catch (err) {
      setState((prev) => ({ ...prev, learningCardsLoading: false }));
      reportError(err, "Could not create learning cards.");
      return null;
    }
  }, [state.activeConv, state.activeModelTag, state.learningCardsLoading, state.streaming, pushToast, reportError]);

  const createDomain = useCallback(
    async (name: string, prompt: string) => {
      const trimmed = name.trim();
      if (!trimmed) {
        pushToast("Name is required.");
        return;
      }
      try {
        const domain = await api.createDomain(trimmed, prompt.trim());
        setState((prev) => ({ ...prev, domains: [...prev.domains, { ...domain, expanded: true, subdomains: [] }] }));
        await selectScope(domain.id, null);
        pushToast("Domain created.");
      } catch (err) {
        reportError(err, "Could not create domain.");
      }
    },
    [pushToast, reportError, selectScope]
  );

  const createSubdomain = useCallback(
    async (domainId: string, name: string, prompt: string) => {
      const trimmed = name.trim();
      if (!trimmed) {
        pushToast("Name is required.");
        return;
      }
      try {
        const sub = await api.createSubdomain(domainId, trimmed, prompt.trim());
        setState((prev) => ({
          ...prev,
          domains: prev.domains.map((d) =>
            d.id === domainId ? { ...d, expanded: true, subdomains: [...d.subdomains, sub] } : d
          ),
        }));
        await selectScope(domainId, sub.id);
        pushToast("Sub-domain created.");
      } catch (err) {
        reportError(err, "Could not create sub-domain.");
      }
    },
    [pushToast, reportError, selectScope]
  );

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateScopeField = useCallback(
    (field: "name" | "description" | "prompt", value: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      setState((prev) => ({ ...prev, domains: mapDomains(prev.domains, scopeId, { [field]: value }) }));
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        api.updateDomain(scopeId, { [field]: value }).catch((err) => reportError(err, "Could not save changes."));
      }, 500);
    },
    [state.activeDomainId, state.activeSubdomainId, reportError]
  );

  const setInheritance = useCallback(
    async (policy: InheritancePolicy) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      setState((prev) => ({ ...prev, domains: mapDomains(prev.domains, scopeId, { inheritance: policy }) }));
      try {
        await api.updateDomain(scopeId, { inheritance: policy });
      } catch (err) {
        reportError(err, "Could not save inheritance setting.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, reportError]
  );

  const setShareWithSiblings = useCallback(
    async (share: boolean) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      setState((prev) => ({ ...prev, domains: mapDomains(prev.domains, scopeId, { shareWithSiblings: share }) }));
      try {
        await api.updateDomain(scopeId, { shareWithSiblings: share });
      } catch (err) {
        reportError(err, "Could not save sibling-sharing setting.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, reportError]
  );

  const uploadDocument = useCallback(
    async (file: File) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      try {
        const doc = await api.uploadDocument(scopeId, file);
        setState((prev) => ({ ...prev, documents: [doc, ...prev.documents] }));
        if (doc.status === "ready") {
          pushToast(`${doc.filename} uploaded (${doc.chunkCount} chunks).`);
        } else {
          pushToast(`${doc.filename}: ${doc.error ?? "processing failed"}`);
        }
      } catch (err) {
        reportError(err, "Could not upload document.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const deleteDocument = useCallback(
    async (documentId: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      try {
        await api.deleteDocument(scopeId, documentId);
        setState((prev) => ({ ...prev, documents: prev.documents.filter((d) => d.id !== documentId) }));
        pushToast("Document deleted.");
      } catch (err) {
        reportError(err, "Could not delete document.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const createDocumentMarkdown = useCallback(
    async (documentId: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return false;
      try {
        const updated = await api.createDocumentMarkdown(scopeId, documentId);
        setState((prev) => ({
          ...prev,
          documents: prev.documents.map((document) => document.id === updated.id ? updated : document),
        }));
        pushToast(`${updated.markdownFilename ?? "Markdown copy"} saved in this document folder.`);
        return true;
      } catch (err) {
        reportError(err, "Could not convert this PDF to Markdown.");
        return false;
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const previewDocument = useCallback(
    async (
      documentId: string,
      variant: "source" | "markdown" = "source",
      ownerScopeId?: string
    ): Promise<DocumentPreview | null> => {
      const scopeId = ownerScopeId ?? state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return null;
      try {
        return await api.getDocumentPreview(scopeId, documentId, variant);
      } catch (err) {
        reportError(err, "Could not open this document.");
        return null;
      }
    },
    [state.activeDomainId, state.activeSubdomainId, reportError]
  );

  const downloadDocumentMarkdown = useCallback(
    async (documentId: string, filename: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return false;
      try {
        const blob = await api.exportDocumentMarkdown(scopeId, documentId);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        const stem = filename.replace(/\.[^.]+$/, "").replace(/[\\/:*?"<>|]/g, "_") || "document";
        link.href = url;
        link.download = `${stem}.md`;
        link.click();
        window.URL.revokeObjectURL(url);
        pushToast(`${stem}.md downloaded.`);
        return true;
      } catch (err) {
        reportError(err, "Could not convert this PDF to Markdown.");
        return false;
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const previewDocumentOrganization = useCallback(
    async (modelTag: string | null): Promise<DocumentOrganizationPreview | null> => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return null;
      try {
        return await api.previewDocumentOrganization(scopeId, modelTag);
      } catch (err) {
        reportError(err, "Could not generate an organization preview.");
        return null;
      }
    },
    [state.activeDomainId, state.activeSubdomainId, reportError]
  );

  const applyDocumentOrganization = useCallback(
    async (
      documentSetHash: string,
      suggestions: DocumentOrganizationSuggestion[]
    ): Promise<boolean> => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return false;
      try {
        const documents = await api.applyDocumentOrganization(scopeId, documentSetHash, suggestions);
        setState((prev) => ({ ...prev, documents }));
        pushToast("Document organization applied.");
        return true;
      } catch (err) {
        reportError(err, "Could not apply the document organization.");
        return false;
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const uploadRepository = useCallback(
    async (file: File, name?: string, revisionLabel?: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      try {
        const repository = await api.uploadRepository(scopeId, file, name, revisionLabel);
        setState((prev) => ({ ...prev, repositories: [repository, ...prev.repositories] }));
        if (repository.status === "ready") {
          pushToast(`${repository.name} indexed (${repository.fileCount} files, ${repository.chunkCount} chunks).`);
        } else {
          pushToast(`${repository.name}: ${repository.error ?? "repository indexing failed"}`);
        }
      } catch (err) {
        reportError(err, "Could not import repository snapshot.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const replaceRepository = useCallback(
    async (repositoryId: string, file: File, revisionLabel?: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      try {
        const repository = await api.replaceRepository(scopeId, repositoryId, file, revisionLabel);
        setState((prev) => ({
          ...prev,
          repositories: prev.repositories.map((item) => (item.id === repositoryId ? repository : item)),
        }));
        pushToast(`${repository.name} snapshot replaced.`);
      } catch (err) {
        reportError(err, "Could not replace repository snapshot; the previous snapshot is still active.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const deleteRepository = useCallback(
    async (repositoryId: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      try {
        const cleanupComplete = await api.deleteRepository(scopeId, repositoryId);
        setState((prev) => ({
          ...prev,
          repositories: prev.repositories.filter((item) => item.id !== repositoryId),
        }));
        pushToast(
          cleanupComplete
            ? "Repository snapshot deleted."
            : "Repository index was deleted, but stored-file cleanup is incomplete."
        );
      } catch (err) {
        reportError(err, "Could not delete repository snapshot.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const createMemory = useCallback(
    async (content: string, conversationId?: string | null) => {
      const trimmed = content.trim();
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!trimmed || !scopeId) return;
      try {
        const memory = await api.createMemory(scopeId, trimmed, conversationId);
        setState((prev) => ({ ...prev, memories: [memory, ...prev.memories] }));
        pushToast("Memory saved.");
      } catch (err) {
        reportError(err, "Could not save memory.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const updateMemory = useCallback(
    async (memoryId: string, content: string) => {
      const trimmed = content.trim();
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!trimmed || !scopeId) return;
      try {
        const memory = await api.updateMemory(scopeId, memoryId, trimmed);
        setState((prev) => ({
          ...prev,
          memories: prev.memories.map((m) => (m.id === memoryId ? memory : m)),
        }));
        pushToast("Memory updated.");
      } catch (err) {
        reportError(err, "Could not update memory.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const deleteMemory = useCallback(
    async (memoryId: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId) return;
      try {
        await api.deleteMemory(scopeId, memoryId);
        setState((prev) => ({ ...prev, memories: prev.memories.filter((m) => m.id !== memoryId) }));
        pushToast("Memory deleted.");
      } catch (err) {
        reportError(err, "Could not delete memory.");
      }
    },
    [state.activeDomainId, state.activeSubdomainId, pushToast, reportError]
  );

  const deleteConversation = useCallback(
    async (conversationId: string) => {
      const scopeId = state.activeSubdomainId ?? state.activeDomainId;
      if (!scopeId || state.streaming) return false;
      try {
        await api.deleteConversation(scopeId, conversationId);
        const remaining = state.conversations.filter((conversation) => conversation.id !== conversationId);
        const deletingActive = state.activeConvId === conversationId;
        setState((prev) => ({
          ...prev,
          conversations: remaining,
          activeConv: deletingActive ? null : prev.activeConv,
          activeConvId: deletingActive ? null : prev.activeConvId,
          ...(deletingActive
            ? {
                promptLayers: [],
                promptPreviewStatus: "idle" as const,
                promptPreviewSource: "draft" as const,
                promptPreviewDraft: "",
                promptPreviewError: null,
              }
            : {}),
        }));
        if (state.activeConvId === conversationId && remaining[0]) {
          await selectConversation(remaining[0].id);
        }
        pushToast("Conversation deleted.");
        return true;
      } catch (err) {
        reportError(err, "Could not delete the conversation.");
        return false;
      }
    },
    [
      state.activeDomainId,
      state.activeSubdomainId,
      state.activeConvId,
      state.conversations,
      state.streaming,
      selectConversation,
      pushToast,
      reportError,
    ]
  );

  const deleteScope = useCallback(
    async (scopeId: string) => {
      if (state.streaming) return false;
      const deletingSubdomain = state.activeSubdomainId === scopeId;
      const parentId = deletingSubdomain ? state.activeDomainId : null;
      const remainingDomains = deletingSubdomain
        ? state.domains
        : state.domains.filter((domain) => domain.id !== scopeId);
      try {
        const result = await api.deleteDomain(scopeId);
        setState((prev) => ({
          ...prev,
          domains: deletingSubdomain
            ? prev.domains.map((domain) =>
                domain.id === parentId
                  ? { ...domain, subdomains: domain.subdomains.filter((sub) => sub.id !== scopeId) }
                  : domain
              )
            : prev.domains.filter((domain) => domain.id !== scopeId),
          activeDomainId: null,
          activeSubdomainId: null,
          activeConv: null,
          activeConvId: null,
          conversations: [],
          promptLayers: [],
          promptPreviewStatus: "idle",
          promptPreviewSource: "draft",
          promptPreviewDraft: "",
          promptPreviewError: null,
          documents: [],
          inheritedDocuments: [],
          repositories: [],
          memories: [],
          inheritedMemories: [],
        }));
        if (parentId) {
          await selectScope(parentId, null);
        } else if (remainingDomains[0]) {
          await selectScope(remainingDomains[0].id, null);
        }
        pushToast(
          result.storageCleanupComplete
            ? deletingSubdomain
              ? "Sub-domain deleted."
              : `Domain and ${result.deletedScopeCount - 1} sub-domain(s) deleted.`
            : "Scope data was deleted, but file cleanup is incomplete. Check backend logs."
        );
        return true;
      } catch (err) {
        reportError(err, "Could not delete the selected scope.");
        return false;
      }
    },
    [
      state.activeDomainId,
      state.activeSubdomainId,
      state.domains,
      state.streaming,
      selectScope,
      pushToast,
      reportError,
    ]
  );

  const loadOptimizerCapabilities = useCallback(
    async (modelTag?: string) => {
      setState((prev) => ({ ...prev, optimizerLoading: true, optimizerError: null }));
      try {
        const optimizerReport = await api.getOptimizerCapabilities(modelTag);
        setState((prev) => ({ ...prev, optimizerReport, optimizerLoading: false, optimizerError: null }));
      } catch (err) {
        const message = err instanceof api.ApiError ? err.message : "Could not create the device report.";
        setState((prev) => ({ ...prev, optimizerLoading: false, optimizerError: message }));
        reportError(err, "Could not create the device report.");
      }
    },
    [reportError]
  );

  const upsertOptimizerRun = useCallback((run: OptimizerRun) => {
    setState((prev) => ({
      ...prev,
      optimizerRuns: [run, ...prev.optimizerRuns.filter((item) => item.id !== run.id)]
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
      optimizerError: null,
    }));
    return run;
  }, []);

  const loadOptimizerRuns = useCallback(async () => {
    setState((prev) => ({ ...prev, optimizerRunsLoading: true, optimizerError: null }));
    try {
      const optimizerRuns = await api.listOptimizerRuns();
      setState((prev) => ({ ...prev, optimizerRuns, optimizerRunsLoading: false }));
      return optimizerRuns;
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not load benchmark history.";
      setState((prev) => ({ ...prev, optimizerRunsLoading: false, optimizerError: message }));
      return [];
    }
  }, []);

  const createOptimizerRun = useCallback(async (
    modelTag: string,
    objective: OptimizerObjective,
    mode: OptimizerMode,
    benchmarkKind: import("./types").OptimizerBenchmarkKind,
  ) => {
    try {
      return upsertOptimizerRun(await api.createOptimizerRun(modelTag, objective, mode, benchmarkKind));
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not prepare the benchmark.";
      setState((prev) => ({ ...prev, optimizerError: message }));
      return null;
    }
  }, [upsertOptimizerRun]);

  const refreshOptimizerRun = useCallback(async (runId: string) => {
    try {
      return upsertOptimizerRun(await api.getOptimizerRun(runId));
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not refresh benchmark progress.";
      setState((prev) => ({ ...prev, optimizerError: message }));
      return null;
    }
  }, [upsertOptimizerRun]);

  const startOptimizerRun = useCallback(async (runId: string) => {
    try {
      return upsertOptimizerRun(await api.startOptimizerRun(runId));
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not start the benchmark.";
      setState((prev) => ({ ...prev, optimizerError: message }));
      return null;
    }
  }, [upsertOptimizerRun]);

  const cancelOptimizerRun = useCallback(async (runId: string) => {
    try {
      return upsertOptimizerRun(await api.cancelOptimizerRun(runId));
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not cancel the benchmark.";
      setState((prev) => ({ ...prev, optimizerError: message }));
      return null;
    }
  }, [upsertOptimizerRun]);

  const deleteOptimizerRun = useCallback(async (runId: string) => {
    try {
      await api.deleteOptimizerRun(runId);
      setState((prev) => ({
        ...prev,
        optimizerRuns: prev.optimizerRuns.filter((item) => item.id !== runId),
        optimizerApplyPreview: prev.optimizerApplyPreview?.runId === runId ? null : prev.optimizerApplyPreview,
        optimizerError: null,
      }));
      pushToast("Benchmark report deleted.");
      return true;
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not delete the benchmark report.";
      setState((prev) => ({ ...prev, optimizerError: message }));
      return false;
    }
  }, [pushToast]);

  const loadOptimizerContextApplyPreview = useCallback(async (runId: string, targetContextLength?: number) => {
    setState((prev) => ({ ...prev, optimizerApplyPreviewLoading: true, optimizerError: null }));
    try {
      const optimizerApplyPreview = await api.getOptimizerContextApplyPreview(runId, targetContextLength);
      setState((prev) => ({
        ...prev,
        optimizerApplyPreview,
        optimizerApplyPreviewLoading: false,
        optimizerError: null,
      }));
      return optimizerApplyPreview;
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not validate this setting change.";
      setState((prev) => ({ ...prev, optimizerApplyPreviewLoading: false, optimizerError: message }));
      return null;
    }
  }, []);

  const loadOptimizerContextAudits = useCallback(async (modelTag?: string) => {
    try {
      const optimizerContextAudits = await api.listOptimizerContextAudits(modelTag);
      setState((prev) => ({ ...prev, optimizerContextAudits, optimizerError: null }));
      return optimizerContextAudits;
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not load context change history.";
      setState((prev) => ({ ...prev, optimizerError: message }));
      return [];
    }
  }, []);

  const applyOptimizerContext = useCallback(async (runId: string, preview: OptimizerContextApplyPreview) => {
    setState((prev) => ({ ...prev, optimizerContextChangeLoading: true, optimizerError: null }));
    try {
      const result = await api.applyOptimizerContext(runId, preview);
      const [activeModelProfile, optimizerContextAudits, optimizerApplyPreview] = await Promise.all([
        api.getActiveModelProfile(),
        api.listOptimizerContextAudits(preview.modelTag),
        api.getOptimizerContextApplyPreview(runId, preview.targetContextLength ?? undefined),
      ]);
      setState((prev) => ({
        ...prev,
        activeModelProfile,
        activeModelTag: activeModelProfile?.tag ?? prev.activeModelTag,
        optimizerContextAudits,
        optimizerApplyPreview,
        optimizerContextChangeLoading: false,
        optimizerError: null,
      }));
      pushToast(`Context changed to ${result.effectiveContextLength.toLocaleString()} tokens and verified.`);
      return result;
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not apply the context change.";
      setState((prev) => ({ ...prev, optimizerContextChangeLoading: false, optimizerError: message }));
      return null;
    }
  }, [pushToast]);

  const rollbackOptimizerContext = useCallback(async (audit: OptimizerContextAudit) => {
    setState((prev) => ({ ...prev, optimizerContextChangeLoading: true, optimizerError: null }));
    try {
      const result = await api.rollbackOptimizerContext(audit.id, audit.newContextLength);
      const [activeModelProfile, optimizerContextAudits] = await Promise.all([
        api.getActiveModelProfile(),
        api.listOptimizerContextAudits(audit.modelTag),
      ]);
      setState((prev) => ({
        ...prev,
        activeModelProfile,
        activeModelTag: activeModelProfile?.tag ?? prev.activeModelTag,
        optimizerContextAudits,
        optimizerApplyPreview: null,
        optimizerContextChangeLoading: false,
        optimizerError: null,
      }));
      pushToast(`Context rolled back to ${result.effectiveContextLength.toLocaleString()} tokens and verified.`);
      return result;
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not roll back the context change.";
      setState((prev) => ({ ...prev, optimizerContextChangeLoading: false, optimizerError: message }));
      return null;
    }
  }, [pushToast]);

  const downloadOptimizerRunReport = useCallback(async (runId: string) => {
    try {
      const blob = await api.getOptimizerRunReport(runId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `optimizer-report-${new Date().toISOString().slice(0, 10)}.md`;
      link.click();
      window.URL.revokeObjectURL(url);
      pushToast("Redacted report downloaded.");
      return true;
    } catch (err) {
      const message = err instanceof api.ApiError ? err.message : "Could not download the report.";
      setState((prev) => ({ ...prev, optimizerError: message }));
      return false;
    }
  }, [pushToast]);

  return {
    state,
    toasts,
    activeDomain,
    activeSubdomain,
    activeScope,
    activeModel,
    activeConvList: state.conversations,
    activeConv: state.activeConv,
    scopePath,
    actions: {
      selectScope,
      selectConversation,
      newConversation,
      setRightMode,
      switchModel,
      saveDomainModelSettings,
      sendMessage,
      stopGeneration,
      regenerate,
      createLearningCards,
      createDomain,
      createSubdomain,
      updateScopeField,
      setInheritance,
      setShareWithSiblings,
      deleteConversation,
      deleteScope,
      pushToast,
      previewPrompt,
      setPromptLayerEnabled,
      uploadDocument,
      deleteDocument,
      createDocumentMarkdown,
      previewDocument,
      downloadDocumentMarkdown,
      previewDocumentOrganization,
      applyDocumentOrganization,
      uploadRepository,
      replaceRepository,
      deleteRepository,
      createMemory,
      updateMemory,
      deleteMemory,
      loadOptimizerCapabilities,
      loadOptimizerRuns,
      createOptimizerRun,
      loadOptimizerContextApplyPreview,
      loadOptimizerContextAudits,
      applyOptimizerContext,
      rollbackOptimizerContext,
      downloadOptimizerRunReport,
      refreshOptimizerRun,
      startOptimizerRun,
      cancelOptimizerRun,
      deleteOptimizerRun,
    },
  };
}

export type Workspace = ReturnType<typeof useWorkspace>;
