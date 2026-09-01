"use client";

import { useEffect, useRef } from "react";

interface HelpModalProps {
  open: boolean;
  onClose: () => void;
}

export function HelpModal({ open, onClose }: HelpModalProps) {
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div
      className={`backdrop${open ? " open" : ""}`}
      ref={backdropRef}
      onMouseDown={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      {open && (
        <div className="modal help-modal">
          <h2>How this workspace works</h2>
          <div className="sub">A quick summary, then a short walkthrough of the basics.</div>

          <div className="help-body scroll">
            <p>
              This is a local LLM workspace. Conversations live inside <b>domains</b> and, optionally,
              one level of <b>sub-domains</b> nested underneath them. Each domain or sub-domain is its
              own scope with its own prompt, documents, and memory — switching scope changes what the
              model knows about and how it behaves, without starting over.
            </p>

            <div className="help-section">
              <h3>1. Pick a model</h3>
              <p>
                Top of the left rail. This is the model every domain and sub-domain uses to answer.
                Only models already pulled in Ollama show up here.
              </p>
            </div>

            <div className="help-section">
              <h3>2. Create a domain</h3>
              <p>
                Use the <b>+</b> next to “Domains” for a top-level scope (e.g. a project or topic), and
                the <b>+ Sub-domain</b> link under it to nest one level inside for a narrower focus. Each
                gets its own scope prompt that shapes how the model responds while that scope is active.
              </p>
            </div>

            <div className="help-section">
              <h3>3. Chat</h3>
              <p>
                Select a domain or sub-domain, then start a conversation in the center column. Use{" "}
                <b>+ New conversation</b> in the left rail to start a fresh thread without losing older
                ones — every conversation in a scope stays listed there.
              </p>
            </div>

            <div className="help-section">
              <h3>4. Inspect, upload, and remember — right rail</h3>
              <ul>
                <li>
                  <b>Prompt inspector</b> — shows the exact layers assembled into the model&apos;s prompt
                  for your current draft, so you can see what&apos;s actually being sent. Expand an
                  implemented background layer to turn it on or off for the selected scope. Turning
                  off framework or model instructions requires an explicit risk acknowledgement;
                  code-level access and isolation controls remain enforced.
                </li>
                <li>
                  <b>Documents</b> — drop in <code>.md</code>, <code>.txt</code>, or <code>.pdf</code>{" "}
                  files to give this scope retrieval (RAG) context. Uploaded text-based PDFs also have
                  a <code>.md</code> control for downloading their extracted text as Markdown. The AI
                  document organizer can propose editable virtual folders and tags; nothing changes until
                  you review and apply the preview. Expand the repository section only when you want to
                  import or update a code snapshot.
                </li>
                <li>
                  <b>Memory</b> — facts or notes this scope should always remember, saved manually or
                  from chat. Adding and reviewing saved memories are separate collapsible sections.
                </li>
                <li>
                  <b>Model Performance Optimizer</b> — inspect device/model placement, run benchmarks,
                  and review diagnostics in separate collapsible sections.
                </li>
                <li>
                  <b>Scope settings</b> — name, description, scope prompt, and whether this scope&apos;s
                  documents/memory/prompt are private or inherited by its children. Identity, sharing,
                  tools, and destructive actions stay separated so only the section you need is open.
                </li>
              </ul>
            </div>

            <div className="help-section">
              <h3>5. Inheritance, in short</h3>
              <p>
                A domain or sub-domain marked <b>Inherited</b> shares its prompt (and, depending on
                settings, documents/memory) with its children. Sub-domains can also optionally share
                their prompt sideways with sibling sub-domains — off by default, toggled in Scope
                settings.
              </p>
            </div>
          </div>

          <div className="modal-actions">
            <button className="btn-primary" onClick={onClose} type="button">
              Got it
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
