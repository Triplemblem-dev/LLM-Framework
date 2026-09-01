"use client";

import { useEffect, useRef, useState } from "react";
import { Workspace } from "../lib/useWorkspace";
import { GenerationMetrics, LearningCardCategory, LearningCardSet } from "../lib/types";
import { SendIcon } from "./icons";
import { MarkdownMessage } from "./MarkdownMessage";

interface ChatColumnProps {
  ws: Workspace;
  draft: string;
  onDraftChange: (value: string) => void;
}

function seconds(milliseconds: number): string {
  return `${(milliseconds / 1000).toFixed(1)}s`;
}

function completedMetrics(metrics: GenerationMetrics): string {
  if (metrics.status === "empty_fallback") return "Empty model response · clarification shown";
  if (metrics.status === "error_fallback") return "Model error · visible fallback shown";
  if (metrics.status === "client_error") return "Connection interrupted · visible fallback shown";
  if (metrics.status === "stopped") return "Generation stopped";
  if (metrics.status === "truncated") return "Answer-length limit reached · continue or adjust Domain model settings";

  const parts: string[] = [];
  if (metrics.outputTokens !== null) parts.push(`${metrics.outputTokens} output tokens`);
  if (metrics.tokensPerSecond !== null) parts.push(`${metrics.tokensPerSecond.toFixed(1)} tok/s`);
  if (metrics.timeToFirstTokenMs !== null) parts.push(`first token ${seconds(metrics.timeToFirstTokenMs)}`);
  if (metrics.totalDurationMs !== null) parts.push(`model time ${seconds(metrics.totalDurationMs)}`);
  return parts.join(" · ") || "Response completed";
}

const CARD_CATEGORY_LABELS: Record<LearningCardCategory, string> = {
  key_idea: "Key idea",
  action: "Action",
  caution: "Keep in mind",
  example: "Example",
};

function LearningCards({ deck }: { deck: LearningCardSet }) {
  return (
    <section className="learning-deck" aria-label={`Learning cards: ${deck.title}`}>
      <div className="learning-deck-head">
        <span className="learning-deck-kicker">Learning cards</span>
        <span>{deck.cards.length} cards</span>
      </div>
      <h3>{deck.title}</h3>
      <p className="learning-deck-summary">{deck.summary}</p>
      <div className="learning-card-grid">
        {deck.cards.map((card, index) => (
          <article className={`learning-card ${card.category}`} key={`${card.title}-${index}`}>
            <span className="learning-card-label">{CARD_CATEGORY_LABELS[card.category]}</span>
            <h4>{card.title}</h4>
            <p>{card.takeaway}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ChatColumn({ ws, draft, onDraftChange }: ChatColumnProps) {
  const { activeDomain, activeSubdomain, activeConv, activeModel, scopePath, state, actions } = ws;
  const scope = activeSubdomain ?? activeDomain;
  const messagesRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [clock, setClock] = useState(() => Date.now());

  useEffect(() => {
    if (!state.streaming) return;
    setClock(Date.now());
    const timer = window.setInterval(() => setClock(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [state.streaming]);

  useEffect(() => {
    if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
  }, [activeConv, state.streaming]);

  function submit() {
    if (!draft.trim() || state.streaming || !scope || !activeModel) return;
    actions.sendMessage(draft);
    onDraftChange("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  async function copyLatestResponse() {
    const messages = activeConv?.messages ?? [];
    const latest = [...messages].reverse().find((message) => message.role === "assistant") ?? messages.at(-1);
    if (!latest) return;
    try {
      await navigator.clipboard.writeText(latest.text);
      actions.pushToast("Latest response copied.");
    } catch {
      actions.pushToast("Could not copy the latest response.");
    }
  }

  if (!scope) {
    return (
      <main className="chat-col">
        <div className="chat-empty" style={{ margin: "auto" }}>
          {state.loading ? "Loading…" : "No domain selected. Create a domain on the left to get started."}
        </div>
      </main>
    );
  }

  const hasMessages = !!activeConv && activeConv.messages.length > 0;
  const latestAssistant = [...(activeConv?.messages ?? [])]
    .reverse()
    .find((message) => message.role === "assistant");
  const latestAssistantComplete = latestAssistant &&
    latestAssistant.id !== "pending" &&
    !latestAssistant.id.startsWith("local-error-") &&
    !latestAssistant.id.startsWith("stopped-") &&
    (!latestAssistant.generationMetrics || latestAssistant.generationMetrics.status === "completed");
  const canSend = !!draft.trim() && !state.streaming && !!activeModel;
  const modelUnavailable = !!state.activeModelTag && !activeModel;
  const sendDisabledReason = state.streaming
    ? "Wait for the current response or press Stop."
    : !activeModel
      ? modelUnavailable
        ? `The selected model (${state.activeModelTag}) is not installed. Choose an installed model from Main model.`
        : "Choose a model from Main model before sending."
      : !draft.trim()
        ? "Write a message before sending."
        : undefined;
  const generationElapsed = state.generationStartedAt ? Math.max(0, clock - state.generationStartedAt) : 0;
  const generationOnlyElapsed = state.generationFirstTokenAt
    ? Math.max(1, clock - state.generationFirstTokenAt)
    : 0;
  const estimatedTokensPerSecond = generationOnlyElapsed
    ? (state.generationCharacters / 4) / (generationOnlyElapsed / 1000)
    : null;
  const isWelcomeDomain = !activeSubdomain && activeDomain?.slug === "welcome-start-here";

  return (
    <main className="chat-col">
      <div className="scope-banner">
        <div className="l">
          <div className="scope-title">{activeSubdomain ? `${activeDomain!.name} → ${activeSubdomain.name}` : activeDomain!.name}</div>
          <div className="scope-path">{scopePath}</div>
          {scope.description &&
            (isWelcomeDomain ? (
              <details className="scope-description">
                <summary>About this domain</summary>
                <div className="scope-desc">{scope.description}</div>
              </details>
            ) : (
              <div className="scope-desc">{scope.description}</div>
            ))}
        </div>
        <button className="edit-link" onClick={() => actions.setRightMode("settings")} type="button">
          Edit prompt
        </button>
      </div>

      <div className="messages scroll" ref={messagesRef}>
        {!hasMessages ? (
          <div className="chat-empty">
            No messages yet. Anything sent here stays isolated to {scopePath} — nothing here is visible to sibling scopes.
          </div>
        ) : (
          <>
            {activeConv!.messages.map((m, messageIndex) => (
              <div key={m.id} className={`msg ${m.role}`}>
                <div className={`bubble${m.role === "assistant" ? " markdown-message" : ""}`}>
                  {m.role === "assistant" ? <MarkdownMessage content={m.text} /> : m.text}
                </div>
                {m.citations.length > 0 && (
                  <div className="citations">
                    {m.citations.map((c, i) => (
                      <span
                        className={`citation-pill ${c.sourceType}`}
                        key={`${c.sourceType}-${c.repositoryId ?? c.documentId}-${c.chunkIndex}-${i}`}
                        title={
                          c.sourceType === "repository"
                            ? `${c.revisionLabel || c.snapshotHash || "indexed snapshot"} · ${c.scopeName}`
                            : c.scopeName
                        }
                      >
                        {c.sourceType === "repository"
                          ? `${c.repositoryName ?? "Repository"} › ${c.relativePath ?? "source"}${
                              c.startLine !== null && c.endLine !== null
                                ? ` (lines ${c.startLine}–${c.endLine})`
                                : ""
                            }`
                          : `${c.documentName ?? "Document"}${c.heading ? ` › ${c.heading}` : ""}${
                              c.pageNumber !== null ? ` (p. ${c.pageNumber})` : ""
                            }`}
                      </span>
                    ))}
                  </div>
                )}
                <div className="msg-meta">
                  {m.role === "user" ? "you" : "assistant"}
                  {m.role === "assistant" && m.generationMetrics && (
                    <span
                      className={`generation-metrics ${m.generationMetrics.status}`}
                      title="Token speed is reported by Ollama after generation completes. First-token and model times do not include browser rendering."
                    >
                      {completedMetrics(m.generationMetrics)}
                    </span>
                  )}
                  {m.role === "assistant" && state.streaming && messageIndex === activeConv!.messages.length - 1 && (
                    <span className="generation-metrics live" aria-live="polite">
                      Generating · {seconds(generationElapsed)}
                      {estimatedTokensPerSecond !== null
                        ? ` · ~${estimatedTokensPerSecond.toFixed(1)} tok/s estimated`
                        : ""}
                    </span>
                  )}
                  {m.id !== "pending" && (
                    <button
                      className="msg-save-memory"
                      type="button"
                      onClick={() => actions.createMemory(m.text, activeConv?.id ?? null)}
                      title="Save this message as a memory for this scope"
                    >
                      Save as memory
                    </button>
                  )}
                  {m.role === "assistant" && m.id === latestAssistant?.id && (
                    <button
                      type="button"
                      className="msg-learning-cards"
                      disabled={
                        state.streaming ||
                        state.learningCardsLoading ||
                        !latestAssistantComplete ||
                        !activeModel
                      }
                      onClick={actions.createLearningCards}
                      title="Turn this latest response into one short summary and simple learning cards"
                    >
                      {state.learningCardsLoading
                        ? "Making learning cards…"
                        : m.learningCards
                          ? "Refresh learning cards"
                          : "Make learning cards"}
                    </button>
                  )}
                </div>
                {m.role === "assistant" && m.learningCards && <LearningCards deck={m.learningCards} />}
              </div>
            ))}
            {state.streaming && activeConv!.messages[activeConv!.messages.length - 1]?.role !== "assistant" && (
              <div className="msg assistant">
                <div className="bubble generation-waiting" role="status" aria-live="polite">
                  <span className="typing" aria-hidden="true"><i /><i /><i /></span>
                  <span>
                    {state.generationPhase === "preparing_context"
                      ? "Preparing scope, memory, documents, and repository context"
                      : "Context ready · waiting for the model's first token"}
                  </span>
                </div>
                <div className="msg-meta">{seconds(generationElapsed)} elapsed</div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="composer">
        <form
          className="composer-box"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder={
              activeModel
                ? "Message this scope…"
                : modelUnavailable
                  ? "Selected model is not installed…"
                  : "Select a model to start chatting…"
            }
            value={draft}
            onChange={(e) => {
              onDraftChange(e.target.value);
              const el = e.target;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 140) + "px";
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button
            className="send-btn"
            type="submit"
            disabled={!canSend}
            aria-label="Send message"
            title={sendDisabledReason}
          >
            <SendIcon />
          </button>
        </form>
        {!activeModel && (
          <div className="composer-warning" role="status">
            {modelUnavailable
              ? `Cannot send: ${state.activeModelTag} is selected but not installed. Open Main model and choose an installed model.`
              : "Cannot send until a model is selected from Main model."}
          </div>
        )}
        <div className="composer-tools">
          <button type="button" className="ghost-btn" disabled={!state.streaming} onClick={actions.stopGeneration}>
            Stop
          </button>
          <button type="button" className="ghost-btn" disabled={state.streaming || !hasMessages} onClick={actions.regenerate}>
            Regenerate
          </button>
          <button
            type="button"
            className="ghost-btn"
            disabled={!hasMessages}
            onClick={copyLatestResponse}
            title="Copy the latest assistant response"
          >
            Copy
          </button>
        </div>
      </div>
    </main>
  );
}
