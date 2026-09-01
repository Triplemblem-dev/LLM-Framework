"use client";

import { useEffect, useRef, useState } from "react";
import { Workspace } from "../lib/useWorkspace";
import { formatBytes, formatContext } from "../lib/format";
import { ChevronIcon, GearIcon, PlusIcon } from "./icons";

interface LeftRailProps {
  ws: Workspace;
  open: boolean;
  onNewDomain: () => void;
  onNewSubdomain: (domainId: string) => void;
  onDeleteConversation: (conversationId: string, title: string) => void;
}

export function LeftRail({ ws, open, onNewDomain, onNewSubdomain, onDeleteConversation }: LeftRailProps) {
  const { state, activeModel, activeConvList, activeScope, actions } = ws;
  const [modelOpen, setModelOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setModelOpen(false);
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  function openSettingsFor(domainId: string, subId: string | null) {
    actions.selectScope(domainId, subId);
    actions.setRightMode("settings");
  }

  return (
    <aside className={`rail rail-left scroll${open ? " open" : ""}`}>
      <div className="rail-section" style={{ flex: "0 0 auto" }}>
        <div className="rail-h">
          <h3>{activeScope ? "Domain model" : "Framework model"}</h3>
        </div>
        <div className="model-wrap" ref={wrapRef}>
          <button className="model-card" onClick={() => setModelOpen((v) => !v)} type="button">
            {activeModel ? (
              <>
                <span className="model-name">{activeModel.name}</span>
                <span className="model-meta">
                  {activeModel.quantizationLevel && <span className="spec">{activeModel.quantizationLevel}</span>}
                  <span className="spec" title="Total request window shared by instructions, documents, conversation history, and the answer">
                    {formatContext(state.domainModelSettings?.contextLength ?? state.activeModelProfile?.contextLength ?? null)} request
                  </span>
                  {state.domainModelSettings && <span className="spec" title="Maximum tokens reserved for each answer">{formatContext(state.domainModelSettings.maxOutputTokens)} answer</span>}
                  <span className="spec">{formatBytes(activeModel.sizeBytes)}</span>
                </span>
              </>
            ) : (
              <>
                <span className="model-name">
                  {state.activeModelTag ? "Selected model unavailable" : "No model selected"}
                </span>
                {state.activeModelTag && <span className="model-meta">{state.activeModelTag} is not installed</span>}
              </>
            )}
          </button>
          <div className={`popover${modelOpen ? " open" : ""}`}>
            {state.models.length === 0 ? (
              <div className="conv-empty">
                {state.modelsUnreachable
                  ? "Could not reach Ollama. Confirm it's running."
                  : "No models installed. Run `ollama pull <model>` on the server."}
              </div>
            ) : (
              state.models.map((m) => (
                <button
                  key={m.tag}
                  className={`popover-item${m.tag === state.activeModelTag ? " sel" : ""}`}
                  onClick={() => {
                    actions.switchModel(m.tag);
                    setModelOpen(false);
                  }}
                  type="button"
                >
                  <div className="row1">
                    <b>{m.name}</b>
                    {m.quantizationLevel && <span className="tag candidate">{m.quantizationLevel}</span>}
                  </div>
                  <span className="model-meta">
                    <span className="spec" title="Model's native context limit">{formatContext(m.contextLength)} native</span>
                    <span className="spec">{formatBytes(m.sizeBytes)}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
        <div className="status-line">
          <span className={`dot${state.modelsUnreachable ? "" : " ok"}`} />
          <span>{state.modelsUnreachable ? "Ollama · not reachable" : "Ollama · connected"}</span>
        </div>
      </div>

      <div className="rail-section" style={{ flex: "1 1 auto", minHeight: 120 }}>
        <div className="rail-h">
          <h3>Domains</h3>
          <button className="rail-add" onClick={onNewDomain} title="New domain" aria-label="New domain" type="button">
            <PlusIcon />
          </button>
        </div>
        <div className="tree-scroll scroll">
          {state.domains.length === 0 && !state.loading && (
            <div className="conv-empty">No domains yet. Create one to get started.</div>
          )}
          {state.domains.map((d) => {
            const domainActive = d.id === state.activeDomainId && !state.activeSubdomainId;
            const chevCls = d.expanded ? "open" : "";
            return (
              <div key={d.id}>
                <div
                  className={`drow${domainActive ? " active" : ""}`}
                  onClick={() => actions.selectScope(d.id, null)}
                >
                  <button
                    className={`chev ${chevCls}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      actions.selectScope(d.id, null);
                    }}
                    type="button"
                    aria-label={d.expanded ? `${d.name} selected` : `Select and expand ${d.name}`}
                  >
                    <ChevronIcon />
                  </button>
                  <span className="name">{d.name}</span>
                  <button
                    className="scope-add"
                    onClick={(e) => {
                      e.stopPropagation();
                      onNewSubdomain(d.id);
                    }}
                    title={`New sub-domain in ${d.name}`}
                    aria-label={`New sub-domain in ${d.name}`}
                    type="button"
                  >
                    <PlusIcon />
                  </button>
                  <button
                    className="gear"
                    onClick={(e) => {
                      e.stopPropagation();
                      openSettingsFor(d.id, null);
                    }}
                    title="Domain settings"
                    type="button"
                  >
                    <GearIcon />
                  </button>
                </div>

                {d.expanded && (
                  <>
                    {d.subdomains.length ? (
                      <div className="sub-list">
                        {d.subdomains.map((s) => {
                          const subActive = d.id === state.activeDomainId && s.id === state.activeSubdomainId;
                          return (
                            <div
                              key={s.id}
                              className={`drow sub${subActive ? " active" : ""}`}
                              onClick={() => actions.selectScope(d.id, s.id)}
                            >
                              <span className="chev leaf" />
                              <span className="name">{s.name}</span>
                              <span
                                className={`inh-chip${s.inheritance === "inherited" ? " inherited" : ""}`}
                                title={s.inheritance === "inherited" ? "Uses parent context" : "Does not use parent context"}
                              >
                                {s.inheritance === "inherited" ? "I" : "P"}
                              </span>
                              <button
                                className="gear"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openSettingsFor(d.id, s.id);
                                }}
                                title="Sub-domain settings"
                                type="button"
                              >
                                <GearIcon />
                              </button>
                            </div>
                          );
                        })}
                        <button
                          className="rail-add text"
                          style={{ margin: "4px 0 6px 26px" }}
                          onClick={() => onNewSubdomain(d.id)}
                          title="New sub-domain"
                          type="button"
                        >
                          + Sub-domain
                        </button>
                      </div>
                    ) : (
                      <div className="sub-list">
                        <div className="empty-sub">No sub-domains yet.</div>
                        <button
                          className="rail-add text"
                          style={{ margin: "0 0 8px 26px" }}
                          onClick={() => onNewSubdomain(d.id)}
                          title="New sub-domain"
                          type="button"
                        >
                          + Sub-domain
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="rail-section" style={{ flex: "0 0 auto" }}>
        <div className="rail-h">
          <h3>Conversations</h3>
          <div className="rail-h-actions">
            {state.activeConv && (
              <button
                className="rail-action-danger"
                onClick={() => onDeleteConversation(state.activeConv!.id, state.activeConv!.title)}
                disabled={state.streaming}
                title="Delete selected conversation"
                aria-label="Delete selected conversation"
                type="button"
              >
                −
              </button>
            )}
            <button className="rail-add" onClick={actions.newConversation} title="New conversation" aria-label="New conversation" type="button">
              <PlusIcon />
            </button>
          </div>
        </div>
        <div className="conv-scroll scroll">
          {activeConvList.length === 0 ? (
            <div className="conv-empty">No conversations in this scope yet. Start one below.</div>
          ) : (
            activeConvList.map((c) => (
              <button
                key={c.id}
                className={`crow${c.id === state.activeConvId ? " active" : ""}`}
                onClick={() => actions.selectConversation(c.id)}
                type="button"
              >
                <span className="t">{c.title}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}
