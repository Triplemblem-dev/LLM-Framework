"use client";

import { useState } from "react";
import { useWorkspace } from "../lib/useWorkspace";
import { TopBar } from "./TopBar";
import { LeftRail } from "./LeftRail";
import { ChatColumn } from "./ChatColumn";
import { RightRail } from "./RightRail";
import { Modal } from "./Modal";
import { HelpModal } from "./HelpModal";
import { Toasts } from "./Toasts";

type ModalState = { kind: "domain" } | { kind: "subdomain"; domainId: string; domainName: string } | null;
type DeleteTarget =
  | { kind: "conversation"; id: string; name: string }
  | { kind: "subdomain"; id: string; name: string }
  | { kind: "domain"; id: string; name: string; childCount: number };

export function Workspace() {
  const ws = useWorkspace();
  const { activeDomain, activeSubdomain, activeModel } = ws;

  const [draft, setDraft] = useState("");
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);
  const [formName, setFormName] = useState("");
  const [formPrompt, setFormPrompt] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);

  function closeModal() {
    setModal(null);
    setFormName("");
    setFormPrompt("");
  }

  function confirmModal() {
    if (!modal) return;
    if (modal.kind === "domain") {
      ws.actions.createDomain(formName, formPrompt);
    } else {
      ws.actions.createSubdomain(modal.domainId, formName, formPrompt);
    }
    closeModal();
  }

  function closeDeleteModal() {
    if (deleting) return;
    setDeleteTarget(null);
    setDeleteConfirmation("");
  }

  async function confirmDelete() {
    if (!deleteTarget || deleting) return;
    if (deleteTarget.kind !== "conversation" && deleteConfirmation !== deleteTarget.name) return;
    setDeleting(true);
    const deleted =
      deleteTarget.kind === "conversation"
        ? await ws.actions.deleteConversation(deleteTarget.id)
        : await ws.actions.deleteScope(deleteTarget.id);
    setDeleting(false);
    if (deleted) closeDeleteModal();
  }

  function requestScopeDeletion() {
    if (!ws.activeScope || ws.state.streaming) return;
    if (ws.activeSubdomain) {
      setDeleteTarget({ kind: "subdomain", id: ws.activeSubdomain.id, name: ws.activeSubdomain.name });
    } else if (ws.activeDomain) {
      setDeleteTarget({
        kind: "domain",
        id: ws.activeDomain.id,
        name: ws.activeDomain.name,
        childCount: ws.activeDomain.subdomains.length,
      });
    }
    setDeleteConfirmation("");
  }

  return (
    <div className="app">
      <TopBar
        domain={activeDomain}
        subdomain={activeSubdomain}
        model={activeModel}
        onToggleLeft={() => setLeftOpen((v) => !v)}
        onToggleRight={() => setRightOpen((v) => !v)}
        onOpenHelp={() => setHelpOpen(true)}
      />
      <div className="workspace">
        <LeftRail
          ws={ws}
          open={leftOpen}
          onNewDomain={() => setModal({ kind: "domain" })}
          onNewSubdomain={(domainId) => {
            const d = ws.state.domains.find((x) => x.id === domainId);
            setModal({ kind: "subdomain", domainId, domainName: d ? d.name : "" });
          }}
          onDeleteConversation={(id, name) => {
            if (!ws.state.streaming) setDeleteTarget({ kind: "conversation", id, name });
          }}
        />

        <ChatColumn ws={ws} draft={draft} onDraftChange={setDraft} />

        <RightRail ws={ws} draft={draft} open={rightOpen} onDeleteScope={requestScopeDeletion} />
      </div>

      <Modal
        open={modal !== null}
        title={modal?.kind === "subdomain" ? "New sub-domain" : "New domain"}
        subtitle={
          modal?.kind === "subdomain"
            ? `Nested one level inside ${modal.domainName}. Sub-domains cannot contain another level.`
            : "A top-level scope. It will use the main model with its own prompt."
        }
        confirmLabel="Create"
        onClose={closeModal}
        onConfirm={confirmModal}
      >
        <div className="settings-field">
          <label>Name</label>
          <input
            type="text"
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder={modal?.kind === "subdomain" ? "e.g. Onboarding" : "e.g. Personal Knowledge"}
          />
        </div>
        <div className="settings-field">
          <label>Scope prompt</label>
          <textarea
            rows={3}
            value={formPrompt}
            onChange={(e) => setFormPrompt(e.target.value)}
            placeholder={modal?.kind === "subdomain" ? "You are currently focused only on…" : "You are helping with…"}
          />
        </div>
      </Modal>

      <Modal
        open={deleteTarget !== null}
        title={
          deleteTarget?.kind === "conversation"
            ? "Delete conversation?"
            : deleteTarget?.kind === "subdomain"
              ? "Delete sub-domain?"
              : "Delete domain and all children?"
        }
        subtitle={
          deleteTarget?.kind === "conversation"
            ? "This permanently deletes its messages, citations, and retrieval logs. Saved memories remain but lose their source-conversation link."
            : deleteTarget?.kind === "subdomain"
              ? "This permanently deletes the sub-domain and all of its conversations, messages, documents, document files, memories, and logs."
              : `This permanently deletes the domain, its ${deleteTarget?.kind === "domain" ? deleteTarget.childCount : 0} sub-domain(s), and all conversations, messages, documents, document files, memories, and logs below them.`
        }
        confirmLabel={deleting ? "Deleting…" : "Delete permanently"}
        confirmDanger
        confirmDisabled={
          deleting ||
          !deleteTarget ||
          (deleteTarget.kind !== "conversation" && deleteConfirmation !== deleteTarget.name)
        }
        onClose={closeDeleteModal}
        onConfirm={confirmDelete}
      >
        {deleteTarget?.kind === "conversation" ? (
          <p className="delete-warning">
            Selected conversation: <b>{deleteTarget.name}</b>
          </p>
        ) : (
          <div className="settings-field">
            <label>
              Type <b>{deleteTarget?.name}</b> to confirm
            </label>
            <input
              type="text"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              autoComplete="off"
              autoFocus
            />
          </div>
        )}
      </Modal>

      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />

      <Toasts toasts={ws.toasts} />
    </div>
  );
}
