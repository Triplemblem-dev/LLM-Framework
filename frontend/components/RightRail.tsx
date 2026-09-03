"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Workspace } from "../lib/useWorkspace";
import * as api from "../lib/api";
import { DocumentIcon, EyeIcon, MemoryIcon, NetworkIcon, PerformanceIcon, SlidersIcon } from "./icons";
import {
  CodeRepositoryInfo,
  DocumentInfo,
  DocumentPreview,
  DocumentOrganizationPreview,
  DocumentOrganizationSuggestion,
  DocumentStatus,
  DomainModelSettings,
  InheritedDocumentInfo,
  InheritedMemoryInfo,
  MemoryInfo,
  OptimizerBenchmarkKind,
  OptimizerContextApplyPreview,
  OptimizerMode,
  OptimizerObjective,
  OptimizerPlacement,
  OptimizerRun,
  PromptLayer,
  RemoteAccessMode,
  RemoteAccessStatus,
  RemoteApiKey,
} from "../lib/types";
import { MarkdownMessage } from "./MarkdownMessage";

interface RightRailProps {
  ws: Workspace;
  draft: string;
  open: boolean;
  onDeleteScope: () => void;
}

const TOOLS = [
  { name: "Web research", status: "Planned" },
  { name: "Document search", status: "Active/local" },
  { name: "PDF to Markdown", status: "Active/local" },
  { name: "AI document organizer", status: "Active/local" },
  { name: "Code repository search", status: "Active/local" },
  { name: "Calculator", status: "Planned" },
] as const;

type PanelAccordionValue = {
  openId: string | null;
  setOpenId: (id: string | null) => void;
};

const PanelAccordionContext = createContext<PanelAccordionValue | null>(null);

function PanelAccordion({ children }: { children: ReactNode }) {
  const [openId, setOpenId] = useState<string | null>(null);
  return (
    <PanelAccordionContext.Provider value={{ openId, setOpenId }}>
      {children}
    </PanelAccordionContext.Provider>
  );
}

function PanelSection({
  id,
  title,
  description,
  meta,
  tone = "normal",
  children,
}: {
  id: string;
  title: string;
  description: string;
  meta?: string;
  tone?: "normal" | "danger";
  children: ReactNode;
}) {
  const accordion = useContext(PanelAccordionContext);
  const open = accordion?.openId === id;
  return (
    <details
      className={`panel-section${tone === "danger" ? " danger" : ""}`}
      open={open}
    >
      <summary
        className="panel-section-heading"
        onClick={(event) => {
          event.preventDefault();
          accordion?.setOpenId(open ? null : id);
        }}
      >
        <span className="panel-section-chevron" aria-hidden="true">›</span>
        <span className="panel-section-copy">
          <strong>{title}</strong>
          <small>{description}</small>
        </span>
        {meta && <span className="panel-section-meta">{meta}</span>}
      </summary>
      <div className="panel-section-body">{children}</div>
    </details>
  );
}

export function RightRail({ ws, draft, open, onDeleteScope }: RightRailProps) {
  const { state, actions } = ws;
  const panelHeading =
    state.rightMode === "inspector"
      ? { title: "What the model sees", detail: "How the current message will be assembled" }
      : state.rightMode === "documents"
        ? {
            title: "Documents",
            detail: `${state.documents.length} document(s) · ${state.repositories.length} repository snapshot(s)${state.inheritedDocuments.length ? ` · ${state.inheritedDocuments.length} inherited document(s)` : ""}`,
          }
        : state.rightMode === "memory"
          ? {
              title: "Memory",
              detail: `${state.memories.length} in this scope${state.inheritedMemories.length ? ` · ${state.inheritedMemories.length} inherited` : ""}`,
            }
          : state.rightMode === "optimizer"
            ? { title: "Model Performance Optimizer", detail: "Quick tuning, hardware evidence, and optional benchmarks" }
            : state.rightMode === "remote"
              ? { title: "Remote access", detail: "Private access for your own devices" }
            : { title: "Scope settings", detail: "Configure the selected domain or sub-domain" };

  return (
    <aside className={`rail rail-right${open ? " open" : ""}`}>
      <div className="rr-tabs" aria-label="Right rail panels">
        <button
          className={`rr-tab${state.rightMode === "inspector" ? " on" : ""}`}
          onClick={() => actions.setRightMode("inspector")}
          type="button"
          aria-label="What the model sees"
          aria-pressed={state.rightMode === "inspector"}
          title="What the model sees"
        >
          <EyeIcon />
        </button>
        <button
          className={`rr-tab${state.rightMode === "documents" ? " on" : ""}`}
          onClick={() => actions.setRightMode("documents")}
          type="button"
          aria-label="Documents"
          aria-pressed={state.rightMode === "documents"}
          title="Documents"
        >
          <DocumentIcon />
        </button>
        <button
          className={`rr-tab${state.rightMode === "memory" ? " on" : ""}`}
          onClick={() => actions.setRightMode("memory")}
          type="button"
          aria-label="Memory"
          aria-pressed={state.rightMode === "memory"}
          title="Memory"
        >
          <MemoryIcon />
        </button>
        <button
          className={`rr-tab${state.rightMode === "optimizer" ? " on" : ""}`}
          onClick={() => actions.setRightMode("optimizer")}
          type="button"
          aria-label="Model Performance Optimizer"
          aria-pressed={state.rightMode === "optimizer"}
          title="Model Performance Optimizer"
        >
          <PerformanceIcon />
        </button>
        <button
          className={`rr-tab${state.rightMode === "remote" ? " on" : ""}`}
          onClick={() => actions.setRightMode("remote")}
          type="button"
          aria-label="Remote access"
          aria-pressed={state.rightMode === "remote"}
          title="Remote access"
        >
          <NetworkIcon />
        </button>
        <button
          className={`rr-tab${state.rightMode === "settings" ? " on" : ""}`}
          onClick={() => actions.setRightMode("settings")}
          type="button"
          aria-label="Scope settings"
          aria-pressed={state.rightMode === "settings"}
          title="Scope settings"
        >
          <SlidersIcon />
        </button>
      </div>
      <div className="rr-body scroll">
        <header className="rr-panel-heading">
          <h2>{panelHeading.title}</h2>
          <p>{panelHeading.detail}</p>
        </header>
        <PanelAccordion key={`${state.rightMode}-${ws.activeScope?.id ?? "none"}`}>
          {state.rightMode === "inspector" ? (
            <Inspector ws={ws} draft={draft} />
          ) : state.rightMode === "documents" ? (
            <DocumentsPanel ws={ws} />
          ) : state.rightMode === "memory" ? (
            <MemoryPanel ws={ws} />
          ) : state.rightMode === "optimizer" ? (
            <PerformancePanel ws={ws} />
          ) : state.rightMode === "remote" ? (
            <RemoteAccessPanel ws={ws} />
          ) : (
            <Settings ws={ws} onDeleteScope={onDeleteScope} />
          )}
        </PanelAccordion>
      </div>
    </aside>
  );
}

function RemoteAccessPanel({ ws }: { ws: Workspace }) {
  const [status, setStatus] = useState<RemoteAccessStatus | null>(null);
  const [keys, setKeys] = useState<RemoteApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draftMode, setDraftMode] = useState<RemoteAccessMode>("off");
  const [deviceName, setDeviceName] = useState("");
  const [selectedDomainIds, setSelectedDomainIds] = useState<string[]>([]);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [connectionResult, setConnectionResult] = useState<string | null>(null);
  const [connectionHelpOpen, setConnectionHelpOpen] = useState(false);

  const domains = ws.state.domains.flatMap((domain) => [
    { id: domain.id, path: domain.name },
    ...domain.subdomains.map((subdomain) => ({
      id: subdomain.id,
      path: `${domain.name} / ${subdomain.name}`,
    })),
  ]);

  async function refresh() {
    try {
      const [nextStatus, nextKeys] = await Promise.all([
        api.getRemoteAccess(),
        api.listRemoteApiKeys(),
      ]);
      setStatus(nextStatus);
      setDraftMode(nextStatus.mode);
      setKeys(nextKeys);
    } catch (error) {
      ws.actions.pushToast(error instanceof api.ApiError ? error.message : "Could not load remote access settings.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function saveMode() {
    if (draftMode !== "off" && status?.mode === "off") {
      const confirmed = window.confirm(
        "Enable remote API access? Only devices with a key and an approved domain can connect. The HTTPS gateway must also be configured and running."
      );
      if (!confirmed) return;
    }
    setSaving(true);
    try {
      const nextStatus = await api.updateRemoteAccess(draftMode, status?.gatewayPort ?? 8443);
      setStatus(nextStatus);
      ws.actions.pushToast(nextStatus.mode === "off" ? "Remote access is off." : "Remote access mode saved.");
    } catch (error) {
      ws.actions.pushToast(error instanceof api.ApiError ? error.message : "Could not update remote access.");
      setDraftMode(status?.mode ?? "off");
    } finally {
      setSaving(false);
    }
  }

  function toggleDomain(domainId: string) {
    setSelectedDomainIds((current) =>
      current.includes(domainId) ? current.filter((id) => id !== domainId) : [...current, domainId]
    );
  }

  async function createKey() {
    if (!deviceName.trim() || selectedDomainIds.length === 0) {
      ws.actions.pushToast("Enter a device name and select at least one domain.");
      return;
    }
    setSaving(true);
    try {
      const created = await api.createRemoteApiKey(deviceName.trim(), selectedDomainIds);
      setKeys((current) => [created, ...current]);
      setNewToken(created.token);
      setDeviceName("");
      setSelectedDomainIds([]);
      ws.actions.pushToast("Device key created. Copy it now; it will not be shown again.");
    } catch (error) {
      ws.actions.pushToast(error instanceof api.ApiError ? error.message : "Could not create the device key.");
    } finally {
      setSaving(false);
    }
  }

  async function revokeKey(item: RemoteApiKey) {
    if (!window.confirm(`Revoke access for “${item.name}”? That device will stop working immediately.`)) return;
    try {
      await api.revokeRemoteApiKey(item.id);
      setKeys((current) => current.map((key) => key.id === item.id ? { ...key, revokedAt: new Date().toISOString() } : key));
      ws.actions.pushToast("Device key revoked.");
    } catch (error) {
      ws.actions.pushToast(error instanceof api.ApiError ? error.message : "Could not revoke the device key.");
    }
  }

  async function copyToken() {
    if (!newToken) return;
    await navigator.clipboard.writeText(newToken);
    ws.actions.pushToast("Device key copied.");
  }

  async function downloadCertificate() {
    try {
      const blob = await api.getRemoteGatewayCertificate();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "llm-framework-ca.crt";
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      ws.actions.pushToast(error instanceof api.ApiError ? error.message : "Could not download the certificate.");
    }
  }

  async function copyApiUrl() {
    if (!status) return;
    await navigator.clipboard.writeText(status.apiBaseUrl);
    ws.actions.pushToast("API base URL copied.");
  }

  async function testConnection() {
    try {
      const result = await api.testRemoteConnection();
      setConnectionResult(result.detail);
      if (result.ready) ws.actions.pushToast("Gateway connection test passed.");
    } catch (error) {
      ws.actions.pushToast(error instanceof api.ApiError ? error.message : "Could not test the gateway.");
    }
  }

  if (loading) return <p className="empty-state">Loading remote access…</p>;

  return (
    <>
      <PanelSection
        id="remote-mode"
        title="Connection mode"
        description="Off by default; choose where your own devices may connect"
        meta={status?.mode === "off" ? "Off" : status?.mode === "local_network" ? "Local network" : "Private VPN"}
      >
        <div className={`remote-status ${status?.mode === "off" ? "off" : "on"}`}>
          <strong>{status?.mode === "off" ? "Remote access is blocked" : "Remote API access is enabled"}</strong>
          <span>{status?.gatewayRunning ? "Secure gateway is running" : status?.gatewayConfigured ? "Gateway configured but not running" : "Gateway setup is incomplete"}</span>
        </div>
        <div className="settings-field">
          <div className="settings-label-row">
            <label htmlFor="remote-connection-mode">Access from</label>
            <button
              className="field-help-button"
              type="button"
              aria-label="Explain remote access connection modes"
              title="How to set up remote access"
              onClick={() => setConnectionHelpOpen(true)}
            >
              ?
            </button>
          </div>
          <select id="remote-connection-mode" value={draftMode} onChange={(event) => setDraftMode(event.target.value as RemoteAccessMode)}>
            <option value="off">Off — this computer only</option>
            <option value="local_network">Local network — same Wi-Fi / LAN</option>
            <option value="private_vpn">Private VPN — Tailscale</option>
          </select>
        </div>
        <button className="btn-primary remote-full-button" type="button" onClick={saveMode} disabled={saving || draftMode === status?.mode}>
          {saving ? "Saving…" : "Apply mode"}
        </button>
        {!status?.gatewayConfigured && (
          <p className="remote-warning">Set the gateway secret and network address in the private runtime .env, then start the optional gateway. The app will not expose itself automatically.</p>
        )}
        {status?.networkConfigurationError && <p className="remote-warning">{status.networkConfigurationError}</p>}
        {status && <p className="settings-hint">Gateway bind: <code>{status.bindAddress}</code>{status.gatewayTransport === "tailscale_serve" ? " (private host loopback)" : ""}</p>}
      </PanelSection>

      <PanelSection
        id="remote-device-keys"
        title="Device keys"
        description="Give each phone or laptop its own revocable key"
        meta={`${keys.filter((key) => !key.revokedAt).length} active`}
      >
        {newToken && (
          <div className="remote-new-token">
            <strong>Copy this key now</strong>
            <code>{newToken}</code>
            <span>It is shown once and cannot be recovered later.</span>
            <button className="btn-primary" type="button" onClick={copyToken}>Copy key</button>
            <button className="btn-ghost" type="button" onClick={() => setNewToken(null)}>I saved it</button>
          </div>
        )}
        <div className="settings-field">
          <label>Device name</label>
          <input type="text" placeholder="My phone" value={deviceName} onChange={(event) => setDeviceName(event.target.value)} />
        </div>
        <div className="settings-field">
          <label>Allowed domains</label>
          <div className="remote-domain-list">
            {domains.map((domain) => (
              <label key={domain.id}>
                <input type="checkbox" checked={selectedDomainIds.includes(domain.id)} onChange={() => toggleDomain(domain.id)} />
                <span>{domain.path}</span>
              </label>
            ))}
          </div>
        </div>
        <button className="btn-primary remote-full-button" type="button" onClick={createKey} disabled={saving || domains.length === 0}>Create device key</button>
        <div className="remote-key-list">
          {keys.length === 0 ? <p className="empty-state">No device keys yet.</p> : keys.map((key) => (
            <article className={key.revokedAt ? "revoked" : ""} key={key.id}>
              <div><strong>{key.name}</strong><code>{key.tokenPrefix}…</code></div>
              <small>{key.domainIds.length} domain(s) · {key.lastUsedAt ? `last used ${new Date(key.lastUsedAt).toLocaleString()}` : "never used"}</small>
              {key.revokedAt ? <span>Revoked</span> : <button className="btn-danger" type="button" onClick={() => revokeKey(key)}>Revoke</button>}
            </article>
          ))}
        </div>
      </PanelSection>

      <PanelSection
        id="remote-connect"
        title="Connect a device"
        description="Private HTTPS endpoint for your client"
      >
        <p className="panel-intro">Use an OpenAI-compatible client with this base URL:</p>
        <code className="remote-api-url">{status?.apiBaseUrl}</code>
        <div className="remote-connect-actions">
          <button className="btn-ghost" type="button" onClick={copyApiUrl}>Copy base URL</button>
          <button className="btn-ghost" type="button" onClick={testConnection}>Test gateway</button>
        </div>
        {connectionResult && <p className="remote-note">{connectionResult}</p>}
        <p className="settings-hint">Choose a model named <code>domain/&lt;domain-id&gt;</code>. The model list only shows domains approved for that device key.</p>
        {status?.certificateRequired ? (
          status.certificateAvailable ? (
            <button className="btn-ghost remote-full-button" type="button" onClick={downloadCertificate}>Download HTTPS trust certificate</button>
          ) : (
            <p className="remote-warning">The HTTPS certificate becomes available after the gateway starts once.</p>
          )
        ) : (
          <p className="remote-note">Tailscale provides the trusted HTTPS certificate. No framework certificate needs to be installed on the client.</p>
        )}
        {status?.mode === "private_vpn" && <p className="remote-note">Install Tailscale on this computer and the remote device, then sign both into the same private tailnet. Use this host&apos;s displayed <code>.ts.net</code> URL. Model inference remains on this host; no router port forwarding is needed.</p>}
      </PanelSection>

      <RemoteConnectionHelp
        open={connectionHelpOpen}
        onClose={() => setConnectionHelpOpen(false)}
      />
    </>
  );
}

const TAILSCALE_ENV_EXAMPLE = [
  "REMOTE_GATEWAY_SHARED_SECRET=<random value of at least 32 characters>",
  "REMOTE_GATEWAY_TRANSPORT=tailscale_serve",
  "REMOTE_GATEWAY_BIND_ADDRESS=127.0.0.1",
  "REMOTE_GATEWAY_HOSTNAME=<host>.<tailnet>.ts.net",
  "REMOTE_GATEWAY_PORT=8443",
  "REMOTE_GATEWAY_CONTAINER_PORT=80",
  "REMOTE_GATEWAY_PUBLIC_URL=https://<host>.<tailnet>.ts.net",
].join("\n");

const TAILSCALE_START_COMMANDS = [
  "docker compose up -d --build backend frontend",
  "docker compose --profile remote up -d gateway",
  "tailscale serve --bg http://127.0.0.1:8443",
].join("\n");

const TAILSCALE_STOP_COMMANDS = [
  "tailscale serve --https=443 off",
  "docker compose --profile remote stop gateway",
].join("\n");

const LAN_ENV_EXAMPLE = [
  "REMOTE_GATEWAY_SHARED_SECRET=<random value of at least 32 characters>",
  "REMOTE_GATEWAY_TRANSPORT=direct",
  "REMOTE_GATEWAY_BIND_ADDRESS=192.168.1.50",
  "REMOTE_GATEWAY_HOSTNAME=192.168.1.50",
  "REMOTE_GATEWAY_PORT=8443",
  "REMOTE_GATEWAY_CONTAINER_PORT=443",
  "REMOTE_GATEWAY_PUBLIC_URL=https://192.168.1.50:8443",
].join("\n");

const GATEWAY_START_COMMANDS = [
  "docker compose up -d --build backend frontend",
  "docker compose --profile remote up -d gateway",
].join("\n");

function RemoteConnectionHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div
      className={`backdrop${open ? " open" : ""}`}
      ref={backdropRef}
      onMouseDown={(event) => {
        if (event.target === backdropRef.current) onClose();
      }}
    >
      {open && (
        <section className="modal help-modal remote-help-modal" role="dialog" aria-modal="true" aria-labelledby="remote-help-title">
          <h2 id="remote-help-title">Set up remote access</h2>
          <div className="sub">Choose one approach. Run commands from the repository folder.</div>

          <div className="help-body scroll">
            <div className="help-section remote-help-section">
              <h3>Off — this computer only</h3>
              <p>No setup is needed. The framework remains available locally and rejects remote API calls.</p>
              <p>Select <b>Off — this computer only</b>, apply it, and stop any previously configured remote gateway:</p>
              <pre><code>{TAILSCALE_STOP_COMMANDS}</code></pre>
            </div>

            <div className="help-section remote-help-section">
              <h3>Private VPN — Tailscale (recommended)</h3>
              <ol>
                <li>Install Tailscale on the framework host and each remote phone or laptop.</li>
                <li>Sign every device into the same tailnet and enable Tailscale Serve.</li>
                <li>Find the host&apos;s full <code>.ts.net</code> name in Tailscale.</li>
                <li>Add the following to the private <code>.env</code>, replacing both placeholders:</li>
              </ol>
              <pre><code>{TAILSCALE_ENV_EXAMPLE}</code></pre>
              <p>Start the framework and private route:</p>
              <pre><code>{TAILSCALE_START_COMMANDS}</code></pre>
              <p>Select <b>Private VPN — Tailscale</b>, apply it, and create a device key for the client. Use the displayed <code>.ts.net</code> API URL. No framework certificate or router port forwarding is required.</p>
              <p>To end Tailscale access, select <b>Off</b> in the framework and run:</p>
              <pre><code>{TAILSCALE_STOP_COMMANDS}</code></pre>
            </div>

            <div className="help-section remote-help-section">
              <h3>Local network — same Wi-Fi or LAN</h3>
              <ol>
                <li>Find the host computer&apos;s private LAN address, such as <code>192.168.1.50</code>.</li>
                <li>Allow inbound TCP port <code>8443</code> in the host firewall only for the private network.</li>
                <li>Add the following to the private <code>.env</code>, replacing the example address:</li>
              </ol>
              <pre><code>{LAN_ENV_EXAMPLE}</code></pre>
              <p>Start the framework and gateway:</p>
              <pre><code>{GATEWAY_START_COMMANDS}</code></pre>
              <p>Select <b>Local network</b>, apply it, and create a device key. On each client, download and trust the framework HTTPS certificate from <b>Connect a device</b>.</p>
              <p>To end LAN access, select <b>Off</b> in the framework and run:</p>
              <pre><code>docker compose --profile remote stop gateway</code></pre>
            </div>
          </div>

          <div className="modal-actions">
            <button className="btn-primary" type="button" onClick={onClose}>Close</button>
          </div>
        </section>
      )}
    </div>
  );
}

function optimizerBytes(bytes: number | null): string {
  if (bytes === null) return "Unavailable";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit < 2 ? 0 : 1)} ${units[unit]}`;
}

function relationshipLabel(value: string): string {
  if (value === "same_runtime") return "Same runtime";
  if (value === "container_service") return "Another container";
  if (value === "native_host") return "Native host from container";
  if (value === "remote") return "Remote endpoint";
  return "Unknown relationship";
}

function optimizerMetric(value: number | null | undefined, unit: string, digits = 1): string {
  return value === null || value === undefined ? "Unavailable" : `${value.toFixed(digits)} ${unit}`;
}

function optimizerElapsed(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt) return "Not started";
  const seconds = Math.max(0, Math.round((new Date(completedAt ?? Date.now()).getTime() - new Date(startedAt).getTime()) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
}

function placementFromModel(model: NonNullable<import("../lib/types").OptimizerReport["selectedModel"]>): OptimizerPlacement {
  return {
    kind: model.placement,
    acceleratorFraction: model.acceleratorFraction,
    loadedSizeBytes: model.loadedSizeBytes,
    acceleratorSizeBytes: model.acceleratorSizeBytes,
    source: "Ollama /api/ps",
  };
}

function HardwareAllocation({ placement, backend }: { placement: OptimizerPlacement | null; backend?: string | null }) {
  const known = placement !== null && placement.kind !== "unknown";
  const acceleratorFraction = !known
    ? null
    : placement.kind === "cpu"
      ? 0
      : placement.kind === "accelerator"
        ? placement.acceleratorFraction ?? 1
        : placement.acceleratorFraction;
  const acceleratorPercent = acceleratorFraction === null ? null : Math.round(acceleratorFraction * 100);
  const cpuPercent = acceleratorPercent === null ? null : 100 - acceleratorPercent;
  const headline = !known
    ? "Processor use not observed yet"
    : placement.kind === "cpu"
      ? "CPU only — no GPU allocation observed"
      : placement.kind === "accelerator"
        ? `${backend ?? "GPU / accelerator"} is handling the model`
        : `Split between CPU and ${backend ?? "GPU / accelerator"}`;

  return (
    <div className={`hardware-allocation ${placement?.kind ?? "unknown"}`}>
      <div className="hardware-route" aria-hidden="true">
        <span className={`hardware-node cpu${known && (cpuPercent ?? 0) > 0 ? " active" : ""}`}>CPU</span>
        <span className="hardware-route-line">→</span>
        <span className={`hardware-node accelerator${known && (acceleratorPercent ?? 0) > 0 ? " active" : ""}`}>
          {backend ?? "GPU"}
        </span>
      </div>
      <strong>{headline}</strong>
      {known && acceleratorPercent !== null && cpuPercent !== null ? (
        <>
          <div
            className="hardware-bar"
            role="img"
            aria-label={`Observed model allocation: ${cpuPercent}% CPU, ${acceleratorPercent}% GPU or accelerator`}
          >
            {cpuPercent > 0 && <span className="hardware-bar-cpu" style={{ width: `${cpuPercent}%` }} />}
            {acceleratorPercent > 0 && <span className="hardware-bar-accelerator" style={{ width: `${acceleratorPercent}%` }} />}
          </div>
          <div className="hardware-legend">
            <span><i className="cpu" />CPU {cpuPercent}%</span>
            <span><i className="accelerator" />{backend ?? "GPU / accelerator"} {acceleratorPercent}%</span>
          </div>
        </>
      ) : (
        <span>Run a model benchmark to load the model and observe its actual placement.</span>
      )}
      <small>Source: {placement?.source ?? "waiting for Ollama /api/ps"}</small>
    </div>
  );
}

const ACTIVE_OPTIMIZER_STATES = new Set(["queued", "detecting", "warming", "measuring", "evaluating"]);

function PerformancePanel({ ws }: { ws: Workspace }) {
  const { state, actions } = ws;
  const [targetModel, setTargetModel] = useState(state.activeModelTag ?? state.models[0]?.tag ?? "");
  const [objective, setObjective] = useState<OptimizerObjective>("balanced");
  const [mode, setMode] = useState<OptimizerMode>("quick");
  const [benchmarkKind, setBenchmarkKind] = useState<OptimizerBenchmarkKind>("context_comparison");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const loadReport = actions.loadOptimizerCapabilities;

  useEffect(() => {
    const requested = targetModel || undefined;
    const reportMatches = state.optimizerReport?.requestedModelTag === (requested ?? null);
    if (!state.optimizerLoading && !reportMatches) loadReport(requested);
  }, [loadReport, state.optimizerLoading, state.optimizerReport?.requestedModelTag, targetModel]);

  useEffect(() => {
    void actions.loadOptimizerRuns().then((runs) => {
      const firstRun = runs[0];
      if (firstRun) setSelectedRunId((current) => current ?? firstRun.id);
    });
  }, [actions.loadOptimizerRuns]);

  const selectedRun = state.optimizerRuns.find((run) => run.id === selectedRunId) ?? null;
  const applyPreview = state.optimizerApplyPreview?.runId === selectedRunId
    ? state.optimizerApplyPreview
    : null;
  const auditModelTag = selectedRun?.modelTag ?? targetModel;
  useEffect(() => {
    if (auditModelTag) void actions.loadOptimizerContextAudits(auditModelTag);
  }, [actions.loadOptimizerContextAudits, auditModelTag]);
  useEffect(() => {
    if (!selectedRun || !ACTIVE_OPTIMIZER_STATES.has(selectedRun.state)) return;
    const timer = window.setInterval(() => void actions.refreshOptimizerRun(selectedRun.id), 1200);
    return () => window.clearInterval(timer);
  }, [actions.refreshOptimizerRun, selectedRun?.id, selectedRun?.state]);

  const report = state.optimizerReport;
  const model = report?.selectedModel;
  const runtime = report?.runtimeHost;
  const acceleratorBackend = runtime?.accelerators[0]?.computeBackend ?? null;
  const recommendation = selectedRun?.summary.recommendation;
  const runPlacement = recommendation?.candidate_results.find(
    (item) => item.candidate_id === recommendation.winner_candidate_id
  )?.placement
    ?? selectedRun?.summary.latest_placement
    ?? [...(selectedRun?.candidates.flatMap((item) => item.measurements) ?? [])].reverse().find((item) => item.placement)?.placement
    ?? null;

  const compatibilityReasons: string[] = [];
  if (selectedRun && report) {
    if (report.requestedModelTag !== selectedRun.modelTag) {
      compatibilityReasons.push("The live inspection is for another model; select this run's model to verify its evidence.");
    } else {
      const measuredModel = selectedRun.hardwareSnapshot?.selectedModel;
      if (measuredModel?.digest && report.selectedModel?.digest && measuredModel.digest !== report.selectedModel.digest) {
        compatibilityReasons.push("The installed model build changed after this run.");
      }
      if (selectedRun.ollamaVersion && report.ollama.version && selectedRun.ollamaVersion !== report.ollama.version) {
        compatibilityReasons.push("The Ollama version changed after this run.");
      }
      const measuredRuntime = selectedRun.hardwareSnapshot?.runtimeHost;
      if (measuredRuntime && (
        measuredRuntime.osName !== report.runtimeHost.osName
        || measuredRuntime.osRelease !== report.runtimeHost.osRelease
        || measuredRuntime.cpu.architecture !== report.runtimeHost.cpu.architecture
      )) {
        compatibilityReasons.push("The observed runtime platform changed after this run.");
      }
      const measuredAccelerators = measuredRuntime?.accelerators.map((item) => `${item.name}:${item.computeBackend}`).sort().join("|");
      const currentAccelerators = report.runtimeHost.accelerators.map((item) => `${item.name}:${item.computeBackend}`).sort().join("|");
      if (measuredAccelerators !== undefined && measuredAccelerators !== currentAccelerators) {
        compatibilityReasons.push("The visible accelerator configuration changed after this run.");
      }
    }
  }

  async function prepareRun() {
    if (!targetModel) return;
    const run = await actions.createOptimizerRun(targetModel, objective, mode, benchmarkKind);
    if (run) setSelectedRunId(run.id);
  }

  return (
    <>
      <PanelSection
        id="optimizer-quick-tuning"
        title="Quick model tuning"
        description="Adjust this domain without running a benchmark"
        meta={state.domainModelSettings ? `${Math.round(state.domainModelSettings.contextLength / 1024)}K request` : undefined}
      >
        {ws.activeScope ? (
          <>
            <div className="optimizer-tuning-guide">
              <strong>Hardware fit</strong>
              <span>Model, request context, and answer length affect memory use and speed.</span>
              <strong>Response behaviour</strong>
              <span>Style and temperature affect consistency or creativity, not hardware capacity.</span>
            </div>
            <DomainModelSettingsEditor ws={ws} idPrefix="optimizer" />
          </>
        ) : (
          <p className="empty-state">Select a domain or sub-domain first. Tuning choices are remembered separately for each one.</p>
        )}
      </PanelSection>

      <PanelSection
        id="optimizer-device-report"
        title="Device and model report"
        description="Inspect Ollama, the selected model, and visible hardware"
        meta={report?.ollama.reachable ? "Connected" : report ? "Unavailable" : "Inspecting"}
      >
        <div className="optimizer-readonly">
          <strong>Reports and benchmarks are measurement-only</strong>
          <span>Use Quick model tuning above for ordinary changes. The advanced benchmark apply workflow changes only a reviewed framework-profile context.</span>
        </div>

      <div className="settings-field optimizer-target">
        <label htmlFor="optimizer-model">Model to inspect</label>
        <select
          id="optimizer-model"
          value={targetModel}
          onChange={(event) => setTargetModel(event.target.value)}
          disabled={state.optimizerLoading}
        >
          {state.models.length === 0 && <option value="">No installed model available</option>}
          {state.models.map((item) => <option value={item.tag} key={item.tag}>{item.tag}</option>)}
        </select>
        <button
          className="btn-outline optimizer-refresh"
          type="button"
          onClick={() => loadReport(targetModel || undefined)}
          disabled={state.optimizerLoading}
        >
          {state.optimizerLoading ? "Inspecting…" : "Refresh report"}
        </button>
      </div>

      {state.optimizerError && <p className="optimizer-client-error" role="alert">{state.optimizerError}</p>}
      {state.optimizerLoading && !report && (
        <p className="empty-state" aria-live="polite">Inspecting the framework runtime and configured Ollama endpoint…</p>
      )}

      {report && (
        <>
          <div className="optimizer-captured">
            Captured {new Date(report.capturedAt).toLocaleString()} · schema {report.schemaVersion}
          </div>

          <section className="optimizer-card" aria-labelledby="optimizer-ollama-heading">
            <div className="optimizer-card-heading">
              <h3 id="optimizer-ollama-heading">Ollama connection</h3>
              <span className={`optimizer-status ${report.ollama.reachable ? "available" : "unavailable"}`}>
                {report.ollama.reachable ? "Reachable" : "Unreachable"}
              </span>
            </div>
            <dl className="optimizer-facts">
              <div><dt>Endpoint</dt><dd><code>{report.ollama.endpoint}</code></dd></div>
              <div><dt>Relationship</dt><dd>{relationshipLabel(report.ollama.relationship)}</dd></div>
              <div><dt>Hardware visibility</dt><dd>{report.ollama.hardwareVisibility}</dd></div>
              <div><dt>Ollama version</dt><dd>{report.ollama.version ?? "Unavailable"}</dd></div>
              <div><dt>Installed models</dt><dd>{report.ollama.installedModelCount ?? "Unavailable"}</dd></div>
            </dl>
            {report.ollama.error && (
              <div className="optimizer-inline-error">
                <strong>{report.ollama.error.message}</strong>
                <span>{report.ollama.error.action}</span>
              </div>
            )}
          </section>

          <section className="optimizer-card" aria-labelledby="optimizer-model-heading">
            <div className="optimizer-card-heading">
              <h3 id="optimizer-model-heading">Selected model</h3>
              <span className={`optimizer-status ${model ? "available" : "unavailable"}`}>
                {model ? "Inspected" : "Unavailable"}
              </span>
            </div>
            {model ? (
              <>
                <div className="optimizer-model-name">{model.tag}</div>
                <dl className="optimizer-facts">
                  <div><dt>Parameters</dt><dd>{model.parameterSize ?? "Unavailable"}</dd></div>
                  <div><dt>Quantization</dt><dd>{model.quantizationLevel ?? "Unavailable"}</dd></div>
                  <div><dt>Model file</dt><dd>{optimizerBytes(model.sizeBytes)}</dd></div>
                  <div><dt>Native context</dt><dd>{model.nativeContextLength?.toLocaleString() ?? "Unavailable"}</dd></div>
                  <div><dt>Loaded now</dt><dd>{model.loaded ? "Yes" : "No"}</dd></div>
                  <div><dt>Placement</dt><dd>{model.loaded ? model.placement : "Available after load"}</dd></div>
                  {model.loaded && <div><dt>Ollama loaded allocation</dt><dd>{model.allocatedContextLength?.toLocaleString() ?? "Unavailable"}</dd></div>}
                  {model.loaded && <div><dt>Accelerator allocation</dt><dd>{optimizerBytes(model.acceleratorSizeBytes)} / {optimizerBytes(model.loadedSizeBytes)}</dd></div>}
                </dl>
                <HardwareAllocation
                  placement={model.loaded ? placementFromModel(model) : null}
                  backend={acceleratorBackend}
                />
                {model.loaded && <p className="optimizer-scope-note">This is Ollama&apos;s loaded capacity, not necessarily the context sent by this domain. The actual domain request limit is shown in the left rail and Domain model settings.</p>}
                {model.capabilities.length > 0 && (
                  <div className="optimizer-capability-chips" aria-label="Model capabilities">
                    {model.capabilities.map((capability) => <span key={capability}>{capability}</span>)}
                  </div>
                )}
              </>
            ) : (
              <p className="optimizer-card-empty">Select an installed model and make sure Ollama is reachable.</p>
            )}
          </section>

          {runtime && (
            <section className="optimizer-card" aria-labelledby="optimizer-runtime-heading">
              <div className="optimizer-card-heading">
                <h3 id="optimizer-runtime-heading">Framework runtime</h3>
                <span className={`optimizer-status ${runtime.appliesToOllamaDevice === "yes" ? "available" : "partial"}`}>
                  {runtime.runtimeKind}
                </span>
              </div>
              {runtime.appliesToOllamaDevice !== "yes" && (
                <p className="optimizer-scope-note">These values describe the framework runtime, not the complete Ollama device.</p>
              )}
              <dl className="optimizer-facts">
                <div><dt>Operating system</dt><dd>{runtime.osName} {runtime.osRelease}</dd></div>
                <div><dt>Architecture</dt><dd>{runtime.cpu.architecture}</dd></div>
                <div><dt>CPU</dt><dd>{runtime.cpu.model ?? "Unavailable"}</dd></div>
                <div><dt>CPU cores</dt><dd>{runtime.cpu.physicalCores ?? "?"} physical / {runtime.cpu.logicalCores ?? "?"} logical</dd></div>
                <div><dt>Memory</dt><dd>{optimizerBytes(runtime.memory.availableBytes)} available / {optimizerBytes(runtime.memory.totalBytes)}</dd></div>
                <div><dt>Swap</dt><dd>{optimizerBytes(runtime.memory.swapUsedBytes)} used / {optimizerBytes(runtime.memory.swapTotalBytes)}</dd></div>
                <div><dt>Storage</dt><dd>{optimizerBytes(runtime.storage.availableBytes)} available</dd></div>
              </dl>

              <div className="optimizer-subheading">Visible accelerators</div>
              {runtime.accelerators.length === 0 ? (
                <p className="optimizer-card-empty">No supported accelerator sensor is visible to this runtime.</p>
              ) : runtime.accelerators.map((accelerator, index) => (
                <div className="optimizer-accelerator" key={`${accelerator.name}-${index}`}>
                  <strong>{accelerator.name}</strong>
                  <span>{accelerator.computeBackend ?? "Unknown backend"} · {accelerator.memoryKind} memory</span>
                  <span>
                    {optimizerBytes(accelerator.memoryUsedBytes)} used / {optimizerBytes(accelerator.memoryTotalBytes)}
                    {accelerator.utilizationPercent !== null ? ` · ${accelerator.utilizationPercent}% active` : ""}
                  </span>
                  <span>
                    {accelerator.powerWatts !== null ? `${accelerator.powerWatts} W` : "Power unavailable"}
                    {accelerator.temperatureCelsius !== null ? ` · ${accelerator.temperatureCelsius} °C` : " · temperature unavailable"}
                  </span>
                </div>
              ))}
            </section>
          )}
        </>
      )}
      </PanelSection>

      {report && (
        <PanelSection
          id="optimizer-benchmarks"
          title="Benchmarks and recommendations"
          description="Compare context sizes, review results, and apply a verified choice"
          meta={`${state.optimizerRuns.length} saved`}
        >
          <section className="optimizer-card optimizer-benchmark-plan" aria-labelledby="optimizer-benchmark-heading">
            <div className="optimizer-card-heading">
              <h3 id="optimizer-benchmark-heading">1. Choose benchmark</h3>
              <span className="optimizer-status">Setup only</span>
            </div>
            <p className="optimizer-scope-note">
              Uses built-in test prompts only. Your conversations and documents are not used.
            </p>
            <div className="settings-field">
              <label htmlFor="optimizer-kind">Test type</label>
              <select id="optimizer-kind" value={benchmarkKind} onChange={(event) => setBenchmarkKind(event.target.value as OptimizerBenchmarkKind)}>
                <option value="context_comparison">Compare context sizes · recommended</option>
                <option value="baseline">Current context only</option>
              </select>
              <small className="optimizer-field-help">
                Comparison tests up to four safe context candidates and recommends one for your selected goal. It never applies the result.
              </small>
            </div>
            <div className="settings-field">
              <label htmlFor="optimizer-objective">Goal</label>
              <select id="optimizer-objective" value={objective} onChange={(event) => setObjective(event.target.value as OptimizerObjective)}>
                <option value="balanced">Balanced</option>
                <option value="fast_response">Fast response</option>
                <option value="large_context">Large context</option>
                <option value="low_memory">Low memory</option>
                <option value="low_energy" disabled={!report.capabilities.some((item) => item.key === "power_metrics" && item.status === "available")}>
                  Low energy (sensor required)
                </option>
              </select>
            </div>
            <div className="settings-field">
              <label htmlFor="optimizer-mode">Test length</label>
              <select id="optimizer-mode" value={mode} onChange={(event) => setMode(event.target.value as OptimizerMode)}>
                <option value="quick">Quick · 2 repeats per workload</option>
                <option value="standard">Standard · 3 repeats per workload</option>
              </select>
              <small className="optimizer-field-help">Context comparisons use three synthetic workloads. Repeats are compared only with the same workload.</small>
            </div>
            <button className="btn-outline optimizer-refresh" type="button" onClick={prepareRun} disabled={!model || state.models.length === 0}>
              Create run plan
            </button>
          </section>

          <div className="settings-field optimizer-history-select">
            <label htmlFor="optimizer-history">2. Current or saved run</label>
            <select
              id="optimizer-history"
              value={selectedRunId ?? ""}
              onChange={(event) => setSelectedRunId(event.target.value || null)}
              disabled={state.optimizerRunsLoading || state.optimizerRuns.length === 0}
            >
              {state.optimizerRunsLoading && state.optimizerRuns.length === 0 && <option value="">Loading runs…</option>}
              {!state.optimizerRunsLoading && state.optimizerRuns.length === 0 && <option value="">No run created yet</option>}
              {state.optimizerRuns.map((run) => (
                <option value={run.id} key={run.id}>
                  {new Date(run.createdAt).toLocaleString()} · {run.benchmarkKind === "context_comparison" ? "comparison" : "baseline"} · {run.state}
                </option>
              ))}
            </select>
          </div>

          {selectedRun ? (
            <BenchmarkRunCard
              run={selectedRun}
              placement={runPlacement}
              acceleratorBackend={selectedRun.hardwareSnapshot?.runtimeHost.accelerators[0]?.computeBackend ?? acceleratorBackend}
              onStart={() => actions.startOptimizerRun(selectedRun.id)}
              onCancel={() => actions.cancelOptimizerRun(selectedRun.id)}
              onDownload={() => actions.downloadOptimizerRunReport(selectedRun.id)}
              applyPreview={applyPreview}
              applyPreviewLoading={state.optimizerApplyPreviewLoading}
              onReviewChange={(targetContextLength) => actions.loadOptimizerContextApplyPreview(selectedRun.id, targetContextLength)}
              onApply={() => applyPreview && actions.applyOptimizerContext(selectedRun.id, applyPreview)}
              contextChangeLoading={state.optimizerContextChangeLoading}
              onKeepCurrent={() => actions.pushToast("Current model settings kept. Nothing was changed.")}
              compatibilityReasons={compatibilityReasons}
              onDelete={async () => {
                if (!window.confirm("Delete this local benchmark report and all of its measurements?")) return;
                if (await actions.deleteOptimizerRun(selectedRun.id)) {
                  const remaining = state.optimizerRuns.filter((item) => item.id !== selectedRun.id);
                  setSelectedRunId(remaining[0]?.id ?? null);
                }
              }}
            />
          ) : (
            <section className="optimizer-card optimizer-run optimizer-run-empty" aria-label="Benchmark run status">
              <div className="optimizer-card-heading">
                <h3>3. Run status</h3>
                <span className="optimizer-status">Waiting</span>
              </div>
              <p>Choose the test above and create a run plan. Its progress and results will stay together here.</p>
              <div className="optimizer-progress idle" aria-live="polite">
                <div><strong>Not started</strong><span>0 trials</span></div>
                <progress value={0} max={1} aria-label="Benchmark not started" />
              </div>
            </section>
          )}

          {state.optimizerContextAudits.length > 0 && (
            <section className="optimizer-card optimizer-audit-history" aria-labelledby="optimizer-audit-heading">
              <div className="optimizer-card-heading">
                <h3 id="optimizer-audit-heading">Context change history</h3>
                <span className="optimizer-status available">Verified</span>
              </div>
              <p className="optimizer-scope-note">Append-only local audit records. Rollback is available only while the profile still has the exact applied value.</p>
              {state.optimizerContextAudits.map((audit) => (
                <article key={audit.id}>
                  <div>
                    <strong>{audit.action === "apply" ? "Applied" : "Rolled back"} · {audit.previousContextLength.toLocaleString()} → {audit.newContextLength.toLocaleString()}</strong>
                    <span>{new Date(audit.createdAt).toLocaleString()} · {audit.modelTag}</span>
                  </div>
                  {audit.rollbackAvailable && (
                    <button
                      className="btn-outline"
                      type="button"
                      disabled={state.optimizerContextChangeLoading}
                      onClick={() => {
                        if (!window.confirm(`Roll back ${audit.modelTag} from ${audit.newContextLength.toLocaleString()} to ${audit.previousContextLength.toLocaleString()} context tokens?`)) return;
                        void actions.rollbackOptimizerContext(audit);
                      }}
                    >
                      Roll back
                    </button>
                  )}
                </article>
              ))}
            </section>
          )}
        </PanelSection>
      )}

      {report && (
        <PanelSection
          id="optimizer-discovery"
          title="Discovery details"
          description="Review available sensors, evidence gaps, and warnings"
          meta={`${report.capabilities.length} checks${report.warnings.length ? ` · ${report.warnings.length} warning(s)` : ""}`}
        >
          <div className="optimizer-coverage">
            {report.capabilities.map((capability) => (
              <details key={capability.key}>
                <summary>
                  <span>{capability.label}</span>
                  <span className={`optimizer-status ${capability.status}`}>{capability.status}</span>
                </summary>
                <p>{capability.detail}</p>
                <small>Source: {capability.source}</small>
              </details>
            ))}
          </div>

          {report.warnings.length > 0 && (
            <>
              <div className="optimizer-subheading">What needs attention</div>
              <div className="optimizer-warnings">
                {report.warnings.map((warning) => (
                  <article className={warning.severity} key={warning.code}>
                    <strong>{warning.title}</strong>
                    <p>{warning.detail}</p>
                    {warning.action && <span>Next: {warning.action}</span>}
                  </article>
                ))}
              </div>
            </>
          )}
        </PanelSection>
      )}
    </>
  );
}

function BenchmarkRunCard({
  run,
  placement,
  acceleratorBackend,
  onStart,
  onCancel,
  onDelete,
  onDownload,
  applyPreview,
  applyPreviewLoading,
  onReviewChange,
  onApply,
  contextChangeLoading,
  onKeepCurrent,
  compatibilityReasons,
}: {
  run: OptimizerRun;
  placement: OptimizerPlacement | null;
  acceleratorBackend: string | null;
  onStart: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onDownload: () => void;
  applyPreview: OptimizerContextApplyPreview | null;
  applyPreviewLoading: boolean;
  onReviewChange: (targetContextLength: number) => void;
  onApply: () => void;
  contextChangeLoading: boolean;
  onKeepCurrent: () => void;
  compatibilityReasons: string[];
}) {
  const recommendation = run.summary.recommendation;
  const [applyConfirmed, setApplyConfirmed] = useState(false);
  const [contextChoice, setContextChoice] = useState(
    String(recommendation?.winning_context_length ?? "")
  );
  useEffect(() => setApplyConfirmed(false), [applyPreview?.checkedAt]);
  useEffect(() => {
    setContextChoice(String(recommendation?.winning_context_length ?? ""));
  }, [run.id, recommendation?.winning_context_length]);
  const active = ACTIVE_OPTIMIZER_STATES.has(run.state);
  const terminal = ["completed", "cancelled", "failed"].includes(run.state);
  const progress = run.totalTrials > 0 ? Math.round((run.completedTrials / run.totalTrials) * 100) : 0;
  const medians = run.summary.medians;
  const contextChoiceNumber = Number(contextChoice);
  const contextChoiceValid = Number.isInteger(contextChoiceNumber)
    && contextChoiceNumber >= 512
    && contextChoiceNumber <= 262_144;
  const previewMatchesChoice = applyPreview?.targetContextLength === contextChoiceNumber;
  const allTrials = run.candidates.flatMap((candidate) =>
    candidate.measurements.map((measurement) => ({ candidate, measurement }))
  );
  const contexts = run.candidates.map((candidate) => candidate.settings.num_ctx).filter((value): value is number => value !== undefined);
  const currentCandidate = run.candidates.find((candidate) => candidate.settings.is_current) ?? run.candidates[0];
  const winningCandidate = recommendation?.candidate_results.find(
    (candidate) => candidate.candidate_id === recommendation.winner_candidate_id
  );
  const comparison = run.benchmarkKind === "context_comparison";

  return (
    <section className="optimizer-card optimizer-run" aria-labelledby={`optimizer-run-${run.id}`}>
      <div className="optimizer-card-heading">
        <h3 id={`optimizer-run-${run.id}`}>3. Run status</h3>
        <span className={`optimizer-status ${run.state === "failed" ? "unavailable" : run.state === "completed" ? "available" : "partial"}`}>
          {run.state}
        </span>
      </div>
      <div className="optimizer-run-title">
        <strong>{comparison ? "Context comparison" : "Current baseline"}</strong>
        <span>{run.modelTag}</span>
      </div>
      <dl className="optimizer-facts optimizer-run-summary">
        <div><dt>Goal</dt><dd>{run.objective.replace("_", " ")}</dd></div>
        <div><dt>Test length</dt><dd>{run.mode}</dd></div>
        <div><dt>Candidates</dt><dd>{run.candidates.length} · {contexts.length ? `${Math.min(...contexts).toLocaleString()}–${Math.max(...contexts).toLocaleString()}` : "Default"} tokens</dd></div>
        <div><dt>Estimated time</dt><dd>up to {Math.ceil(run.estimatedSeconds / 60)} minutes</dd></div>
      </dl>
      {comparison && (
        <div className="optimizer-candidate-plan" aria-label="Planned context candidates">
          {run.candidates.map((candidate) => (
            <span className={candidate.settings.is_current ? "current" : ""} key={candidate.id}>
              {candidate.settings.num_ctx?.toLocaleString() ?? "Default"}
              {candidate.settings.is_current ? " · current" : ""}
            </span>
          ))}
        </div>
      )}
      <p className="optimizer-disruption">{run.disruptionNotice}</p>

      <div className={`optimizer-progress${run.state === "planned" ? " idle" : ""}`} aria-live="polite">
        <div>
          <strong>{run.state === "planned" ? "Ready to run" : run.currentStageDetail ?? run.state}</strong>
          <span>{run.completedTrials} / {run.totalTrials} trials · {run.state === "planned" ? `up to ${Math.ceil(run.estimatedSeconds / 60)} min` : optimizerElapsed(run.startedAt, run.completedAt)}</span>
        </div>
        <progress value={run.completedTrials} max={Math.max(1, run.totalTrials)} aria-label={`Benchmark ${progress}% complete`} />
      </div>

      <details className="optimizer-run-details">
        <summary>Technical run details</summary>
        <dl className="optimizer-facts">
          <div><dt>Endpoint</dt><dd><code>{run.endpointDisplay}</code></dd></div>
          <div><dt>Workload</dt><dd>{run.workloadVersion}</dd></div>
          <div><dt>Runner</dt><dd>{run.runnerVersion}</dd></div>
          <div><dt>Ollama</dt><dd>{run.ollamaVersion ?? "Unavailable"}</dd></div>
          <div><dt>Created</dt><dd>{new Date(run.createdAt).toLocaleString()}</dd></div>
          <div><dt>Starting context</dt><dd>{currentCandidate?.settings.num_ctx?.toLocaleString() ?? "Default"} tokens</dd></div>
          <div><dt>Per response</dt><dd>up to {currentCandidate?.settings.num_predict ?? "?"} tokens</dd></div>
        </dl>
      </details>

      {run.errorMessage && <p className="optimizer-client-error" role="alert">{run.errorMessage}</p>}

      {compatibilityReasons.length > 0 && (
        <div className="optimizer-stale" role="status">
          <strong>Recheck before relying on this report</strong>
          {compatibilityReasons.map((reason) => <span key={reason}>{reason}</span>)}
        </div>
      )}

      <details className="optimizer-run-details">
        <summary>Hardware during this run</summary>
        {(terminal || placement) ? (
          <HardwareAllocation placement={placement} backend={acceleratorBackend} />
        ) : (
          <p>Hardware placement will appear here after the model starts.</p>
        )}
      </details>

      <section className="optimizer-outcome" aria-label="Benchmark results">
        <div className="optimizer-card-heading">
          <h4>Results</h4>
          <span className={`optimizer-status ${recommendation?.winner_candidate_id || medians ? "available" : active ? "partial" : ""}`}>
            {recommendation?.winner_candidate_id || medians ? "Ready" : active ? "Measuring" : terminal ? run.state : "Waiting"}
          </span>
        </div>
        {!medians && !recommendation?.winner_candidate_id && (
          <p className="optimizer-result-placeholder">
            {run.state === "planned"
              ? "Start the benchmark to measure this plan. Results will appear in this section."
              : active
                ? "The run is in progress. Results will appear here when enough measurements are complete."
                : "This run ended without a complete result or recommendation."}
          </p>
        )}

        {!comparison && medians && (
          <div className="optimizer-results" aria-label="Measured baseline medians">
            <article><span>First token</span><strong>{optimizerMetric(medians.ttft_ms, "ms")}</strong></article>
            <article><span>Generation</span><strong>{optimizerMetric(medians.generation_tokens_per_second, "tok/s", 2)}</strong></article>
            <article><span>Prompt processing</span><strong>{optimizerMetric(medians.prompt_tokens_per_second, "tok/s", 2)}</strong></article>
            <article><span>Total latency</span><strong>{optimizerMetric(medians.total_duration_ms, "ms")}</strong></article>
          </div>
        )}

        {recommendation && recommendation.winner_candidate_id && (
          <section className="optimizer-recommendation" aria-label="Context recommendation">
          <div className="optimizer-recommendation-heading">
            <span>Recommended for {run.objective.replace("_", " ")}</span>
            <strong>{recommendation.winning_context_length?.toLocaleString()} tokens</strong>
          </div>
          <p>{recommendation.plain_language}</p>
          <p className="optimizer-recommendation-scope">Scope: this model profile only · not a server-global Ollama setting</p>
          <div className="optimizer-confidence">
            <span className={`optimizer-status ${recommendation.confidence === "high" ? "available" : recommendation.confidence === "low" ? "unavailable" : "partial"}`}>
              {recommendation.confidence} confidence
            </span>
            <span>{winningCandidate?.measured_trials ?? 0} measured trials for the winner</span>
          </div>
          <ul>
            {recommendation.confidence_reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
          {recommendation.deltas_from_current && (
            <dl className="optimizer-deltas">
              <div><dt>Context change</dt><dd>{recommendation.deltas_from_current.context_tokens >= 0 ? "+" : ""}{recommendation.deltas_from_current.context_tokens.toLocaleString()} tokens</dd></div>
              <div><dt>Generation</dt><dd>{recommendation.deltas_from_current.generation_rate_percent === null ? "Unavailable" : `${recommendation.deltas_from_current.generation_rate_percent >= 0 ? "+" : ""}${recommendation.deltas_from_current.generation_rate_percent}%`}</dd></div>
              <div><dt>First token</dt><dd>{recommendation.deltas_from_current.ttft_percent === null ? "Unavailable" : `${recommendation.deltas_from_current.ttft_percent >= 0 ? "+" : ""}${recommendation.deltas_from_current.ttft_percent}%`}</dd></div>
            </dl>
          )}
          <small>Recommendation {recommendation.score_version} · {run.summary.recommendation_evaluated_at ? new Date(run.summary.recommendation_evaluated_at).toLocaleString() : "date unavailable"}</small>
          <div className="settings-field optimizer-context-choice">
            <label htmlFor={`optimizer-context-choice-${run.id}`}>Context tokens to apply</label>
            <input
              id={`optimizer-context-choice-${run.id}`}
              type="number"
              min={512}
              max={262144}
              step={512}
              list={`optimizer-context-options-${run.id}`}
              value={contextChoice}
              onChange={(event) => setContextChoice(event.target.value)}
            />
            <datalist id={`optimizer-context-options-${run.id}`}>
              {recommendation.candidate_results
                .filter((candidate) => candidate.state === "completed")
                .map((candidate) => (
                  <option value={candidate.context_length} key={candidate.candidate_id}>
                    {candidate.context_length === recommendation.winning_context_length ? "Recommended" : "Measured candidate"}
                  </option>
                ))}
            </datalist>
            <small className="optimizer-field-help">
              Choose the recommendation, another measured candidate, or a custom value. Custom values receive an unmeasured-performance warning and still cannot exceed safety or native-model limits.
            </small>
          </div>
          <div className="optimizer-run-actions">
            <button className="btn-primary" type="button" onClick={() => onReviewChange(contextChoiceNumber)} disabled={applyPreviewLoading || !contextChoiceValid}>
              {applyPreviewLoading ? "Checking…" : "Review setting change"}
            </button>
            <button className="btn-outline" type="button" onClick={onKeepCurrent}>Keep current settings</button>
            <button className="btn-outline" type="button" onClick={onDownload}>Download redacted report</button>
          </div>
          </section>
        )}
      </section>

      {applyPreview && (
        <section className={`optimizer-apply-preview ${applyPreview.status}`} aria-label="Setting change preview">
          <div className="optimizer-card-heading">
            <h3>Setting change preview</h3>
            <span className={`optimizer-status ${applyPreview.status === "ready" ? "available" : applyPreview.status === "blocked" ? "unavailable" : "partial"}`}>
              {applyPreview.status === "no_change" ? "No change" : applyPreview.status}
            </span>
          </div>
          <div className="optimizer-context-change" aria-label="Current and selected context">
            <span>{applyPreview.currentContextLength?.toLocaleString() ?? "Unavailable"}</span>
            <b aria-hidden="true">→</b>
            <strong>{applyPreview.targetContextLength?.toLocaleString() ?? "Unavailable"} tokens</strong>
          </div>
          <p>{applyPreview.affectedScope}</p>
          <dl className="optimizer-facts">
            <div><dt>Profile</dt><dd>{applyPreview.profileActive ? "Currently active" : "Not currently active"}</dd></div>
            <div><dt>Choice</dt><dd>{applyPreview.selectionKind.replaceAll("_", " ")}</dd></div>
            <div><dt>Optimizer recommendation</dt><dd>{applyPreview.recommendedContextLength?.toLocaleString() ?? "Unavailable"}</dd></div>
            <div><dt>Takes effect</dt><dd>Next model request</dd></div>
            <div><dt>Ollama restart</dt><dd>Not required</dd></div>
            <div><dt>Rollback</dt><dd>Previous value saved in immutable audit</dd></div>
            <div><dt>Native model limit</dt><dd>{applyPreview.nativeContextLimit?.toLocaleString() ?? "Unavailable"}</dd></div>
            <div><dt>Safety ceiling</dt><dd>{applyPreview.safetyCeiling.toLocaleString()}</dd></div>
            <div><dt>Hardware check</dt><dd>{applyPreview.evidence.hardwareStatus}</dd></div>
          </dl>
          {applyPreview.blockingReasons.length > 0 && (
            <div className="optimizer-preview-issues blockers">
              <strong>Resolve before applying</strong>
              {applyPreview.blockingReasons.map((issue) => (
                <article key={issue.code}>
                  <b>{issue.title}</b><span>{issue.detail}</span>
                  {issue.action && <small>Next: {issue.action}</small>}
                </article>
              ))}
            </div>
          )}
          {applyPreview.warnings.length > 0 && (
            <div className="optimizer-preview-issues warnings">
              <strong>Review these warnings</strong>
              {applyPreview.warnings.map((issue) => (
                <article key={issue.code}>
                  <b>{issue.title}</b><span>{issue.detail}</span>
                  {issue.action && <small>Next: {issue.action}</small>}
                </article>
              ))}
            </div>
          )}
          {applyPreview.status === "ready" && previewMatchesChoice && (
            <div className="optimizer-apply-consent">
              <label>
                <input
                  type="checkbox"
                  checked={applyConfirmed}
                  onChange={(event) => setApplyConfirmed(event.target.checked)}
                />
                <span>I reviewed the exact change and accept the listed warnings. Save this context for the model profile.</span>
              </label>
              <button
                className="btn-primary"
                type="button"
                disabled={!applyConfirmed || contextChangeLoading}
                onClick={() => {
                  if (!window.confirm(`Apply ${applyPreview.targetContextLength?.toLocaleString()} context tokens to ${applyPreview.modelTag}? The previous value will remain available for rollback.`)) return;
                  onApply();
                }}
              >
                {contextChangeLoading ? "Applying and verifying…" : `Apply ${applyPreview.targetContextLength?.toLocaleString()} context`}
              </button>
            </div>
          )}
          {applyPreview.status === "ready" && !previewMatchesChoice && (
            <p className="optimizer-preview-choice-stale">You changed the token choice after this check. Review the setting change again before Apply is enabled.</p>
          )}
          <small>
            Checked {new Date(applyPreview.checkedAt).toLocaleString()} · Apply rechecks this evidence before saving, and rollback remains guarded by the exact applied value.
          </small>
        </section>
      )}

      <details className="optimizer-evidence-details">
        <summary>Candidate evidence{comparison && recommendation ? ` (${recommendation.candidate_results.length})` : ""}</summary>
        {comparison && recommendation && recommendation.candidate_results.length > 0 ? (
          <div className="optimizer-comparison" aria-label="Context candidate comparison">
          {recommendation.candidate_results.map((candidate) => {
            const isWinner = candidate.candidate_id === recommendation.winner_candidate_id;
            const pareto = recommendation.pareto_candidate_ids.includes(candidate.candidate_id);
            const acceleratorPercent = candidate.placement?.acceleratorFraction === null || candidate.placement?.acceleratorFraction === undefined
              ? candidate.placement?.kind === "accelerator" ? 100 : candidate.placement?.kind === "cpu" ? 0 : null
              : Math.round(candidate.placement.acceleratorFraction * 100);
            return (
              <article className={isWinner ? "winner" : ""} key={candidate.candidate_id}>
                <header>
                  <strong>{candidate.context_length.toLocaleString()} tokens</strong>
                  <span>{candidate.is_current ? "Current" : isWinner ? "Recommended" : pareto ? "Pareto option" : candidate.state}</span>
                </header>
                <dl>
                  <div><dt>Score</dt><dd>{candidate.score ?? "—"}</dd></div>
                  <div><dt>First token</dt><dd>{optimizerMetric(candidate.medians.ttft_ms, "ms")}</dd></div>
                  <div><dt>Generation</dt><dd>{optimizerMetric(candidate.medians.generation_tokens_per_second, "tok/s", 2)}</dd></div>
                  <div><dt>Loaded memory</dt><dd>{optimizerBytes(candidate.loaded_size_bytes)}</dd></div>
                  <div><dt>Power</dt><dd>{optimizerMetric(candidate.medians.power_watts, "W")}</dd></div>
                  <div><dt>Efficiency</dt><dd>{optimizerMetric(candidate.medians.tokens_per_joule, "tok/J", 3)}</dd></div>
                  <div><dt>Placement</dt><dd>{candidate.placement?.kind ?? "unknown"}{acceleratorPercent === null ? "" : ` · ${acceleratorPercent}% accelerator`}</dd></div>
                  <div><dt>Evidence</dt><dd>{candidate.measured_trials} / {candidate.expected_measured_trials} measured</dd></div>
                  <div><dt>Gen. variance</dt><dd>{candidate.variance.generation_rate_cv === null ? "Unavailable" : `${(candidate.variance.generation_rate_cv * 100).toFixed(1)}% CV`}</dd></div>
                  <div><dt>TTFT variance</dt><dd>{candidate.variance.ttft_cv === null ? "Unavailable" : `${(candidate.variance.ttft_cv * 100).toFixed(1)}% CV`}</dd></div>
                </dl>
                {(candidate.error_message || candidate.stop_reason) && <p>{candidate.error_message ?? candidate.stop_reason}</p>}
              </article>
            );
          })}
          <details className="optimizer-score-details">
            <summary>How this recommendation was scored</summary>
            <p>Each dimension is scored separately. Context beyond the synthetic workload's {recommendation.workload_context_need.toLocaleString()}-token need does not automatically win.</p>
            <p>Confidence variance compares repeated runs of the same workload; differences between short, sustained, and controlled-context prompts are not mislabeled as instability.</p>
            <p>Token-per-joule is estimated from the direct accelerator power snapshot and trial wall time. It stays unavailable when a supported power sensor is absent.</p>
            <dl>
              {Object.entries(recommendation.weights).map(([dimension, weight]) => (
                <div key={dimension}><dt>{dimension}</dt><dd>{Math.round(weight * 100)}%</dd></div>
              ))}
            </dl>
            <p>Pareto options are candidates that were not worse on every measured tradeoff.</p>
          </details>
          </div>
        ) : (
          <p>Candidate measurements will be available after a context comparison finishes.</p>
        )}
      </details>

      <details className="optimizer-trials">
        <summary>Trial details ({allTrials.length})</summary>
        {allTrials.length > 0 ? (
          <>
          {allTrials.map(({ candidate, measurement }) => (
            <div key={measurement.id}>
              <strong>{candidate.settings.num_ctx?.toLocaleString() ?? "Default"} context · {measurement.isWarmup ? "Warm-up" : `Trial ${measurement.trialIndex}`} · {measurement.workloadCase.replaceAll("_", " ")}</strong>
              <span>{measurement.state} · {measurement.coldLoad ? "cold load" : "warm/resident"}</span>
              {measurement.state === "completed" && <span>{optimizerMetric(measurement.ttftMs, "ms")} TTFT · {optimizerMetric(measurement.generationTokensPerSecond, "tok/s", 2)}</span>}
              {measurement.errorMessage && <span>{measurement.errorMessage}</span>}
            </div>
          ))}
          </>
        ) : (
          <p>No trial measurements yet.</p>
        )}
      </details>

      <div className="optimizer-run-actions">
        {run.state === "planned" && <button className="btn-primary" type="button" onClick={onStart}>Run benchmark</button>}
        {active && <button className="btn-primary danger" type="button" onClick={onCancel} disabled={run.cancelRequested}>{run.cancelRequested ? "Stopping…" : "Cancel run"}</button>}
        {terminal && !recommendation?.winner_candidate_id && <button className="btn-outline" type="button" onClick={onDownload}>Download redacted report</button>}
        {(terminal || run.state === "planned") && <button className="btn-outline" type="button" onClick={onDelete}>Delete report</button>}
      </div>
      <small className="optimizer-retention">Generated answers are not retained. This report and its setting preview stay local. No setting has been changed.</small>
    </section>
  );
}

type InspectorGroupId = "rules" | "scope" | "knowledge" | "conversation";
type InspectorAction = "settings" | "parent" | "memory" | "documents" | "repositories";

interface InspectorLayerView {
  layer: PromptLayer;
  label: string;
  group: InspectorGroupId;
  action: InspectorAction | null;
  actionLabel: string | null;
}

const INSPECTOR_GROUPS: { id: InspectorGroupId; label: string; description: string }[] = [
  { id: "rules", label: "Rules", description: "Framework and model behaviour" },
  { id: "scope", label: "Scope", description: "Where this assistant should focus" },
  { id: "knowledge", label: "Knowledge", description: "Memories and document passages" },
  { id: "conversation", label: "Conversation", description: "History and your current message" },
];

function layerLabel(layer: PromptLayer): string {
  return layer.name.replace(/^\d+\.\s*/, "");
}

function inspectorAction(layer: PromptLayer): Pick<InspectorLayerView, "action" | "actionLabel"> {
  if (layer.editTarget === "parent_scope") return { action: "parent", actionLabel: "Open parent" };
  if (layer.editTarget === "scope_settings") return { action: "settings", actionLabel: "Edit scope" };
  if (layer.editTarget === "memory") return { action: "memory", actionLabel: "Manage memory" };
  if (layer.editTarget === "documents") return { action: "documents", actionLabel: "Manage documents" };
  if (layer.editTarget === "repositories") return { action: "repositories", actionLabel: "Manage repositories" };
  return { action: null, actionLabel: null };
}

function roleLabel(role: PromptLayer["modelRole"]): string | null {
  if (role === "system") return "System instructions";
  if (role === "conversation") return "Previous chat messages";
  if (role === "user") return "Current user message";
  return null;
}

function Layer({
  view,
  onAction,
  onToggle,
  changing,
  generationActive,
}: {
  view: InspectorLayerView;
  onAction: (action: InspectorAction) => void;
  onToggle: (layer: PromptLayer, enabled: boolean) => void;
  changing: boolean;
  generationActive: boolean;
}) {
  const planned = view.layer.state === "planned";
  const stateLabel = planned
    ? "Planned"
    : view.layer.ownerEnabled === false
      ? "Owner off"
      : view.layer.state === "included"
        ? "Included"
        : "Not included";
  const role = roleLabel(view.layer.modelRole);
  const controllable = view.layer.control === "standard" || view.layer.control === "advanced";
  return (
    <details className={`layer${planned ? " planned" : ""}`}>
      <summary className="layer-h">
        <span className="layer-chevron" aria-hidden="true">›</span>
        <span className="lbl">{view.label}</span>
        <span className={`flag ${planned ? "planned" : view.layer.applied ? "live" : "later"}`}>{stateLabel}</span>
      </summary>
      <div className="layer-explanation">
        <p>{view.layer.reason}</p>
        <span className="layer-source">
          Source: {view.layer.sourceName ?? (planned ? "Planned feature" : "Managed by the framework")}
          {role ? ` · Model role: ${role}` : ""}
        </span>
      </div>
      {controllable && (
        <div className="prompt-layer-control">
          <span>
            <b>{view.layer.ownerEnabled ? "Enabled for this scope" : "Disabled by owner"}</b>
            <small>
              {view.layer.control === "advanced"
                ? "Advanced model-instruction control"
                : "Included with the next message when content is available"}
            </small>
          </span>
          <button
            className="prompt-layer-switch"
            type="button"
            role="switch"
            aria-checked={view.layer.ownerEnabled === true}
            aria-label={`${view.label}: ${view.layer.ownerEnabled ? "enabled" : "disabled"}`}
            disabled={changing || generationActive}
            onClick={() => onToggle(view.layer, view.layer.ownerEnabled !== true)}
          >
            <span aria-hidden="true" />
          </button>
        </div>
      )}
      {view.layer.control === "fixed" && (
        <p className="prompt-layer-fixed">Fixed send action — clear the composer or do not press Send to exclude it.</p>
      )}
      {!planned && <div className="layer-body"><p className="mono">{view.layer.content}</p></div>}
      {view.action && view.actionLabel && (
        <div className="layer-actions">
          <button className="edit-link" onClick={() => onAction(view.action!)} type="button">{view.actionLabel}</button>
        </div>
      )}
    </details>
  );
}

function Inspector({ ws, draft }: { ws: Workspace; draft: string }) {
  const { activeDomain, activeSubdomain, state, actions } = ws;
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [openGroupId, setOpenGroupId] = useState<string | null>(null);
  const [changingLayerKey, setChangingLayerKey] = useState<string | null>(null);
  const [advancedLayer, setAdvancedLayer] = useState<PromptLayer | null>(null);
  const [advancedAcknowledged, setAdvancedAcknowledged] = useState(false);

  useEffect(() => {
    setOpenGroupId(null);
  }, [activeDomain?.id, activeSubdomain?.id]);

  useEffect(() => {
    setAdvancedLayer(null);
    setAdvancedAcknowledged(false);
    setChangingLayerKey(null);
  }, [activeDomain?.id, activeSubdomain?.id]);

  useEffect(() => {
    if (!activeDomain || state.streaming) return;
    const preserveSentSnapshot =
      state.promptPreviewSource === "sent" && draft.trim() === "" && state.promptPreviewDraft.trim() !== "";
    if (preserveSentSnapshot) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => actions.previewPrompt(draft), 750);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, activeDomain?.id, activeSubdomain?.id, state.activeConv?.id, state.streaming]);

  if (!activeDomain) {
    return <p className="empty-state">Select a domain to see its assembled prompt.</p>;
  }

  const activeDomainId = activeDomain.id;
  const views: InspectorLayerView[] = state.promptLayers.map((layer) => {
    const label = layerLabel(layer);
    return {
      layer,
      label,
      group: layer.category,
      ...inspectorAction(layer),
    };
  });
  const includedCount = views.filter((view) => view.layer.state === "included").length;
  const plannedCount = views.filter((view) => view.layer.state === "planned").length;
  const notIncludedCount = views.length - includedCount - plannedCount;
  const preservingSentSnapshot =
    state.promptPreviewSource === "sent" &&
    state.promptPreviewStatus === "up_to_date" &&
    draft.trim() === "" &&
    state.promptPreviewDraft.trim() !== "";
  const draftChanged = !state.streaming && !preservingSentSnapshot && draft !== state.promptPreviewDraft;
  const statusClass =
    state.promptPreviewStatus === "unavailable"
      ? "unavailable"
      : state.promptPreviewStatus === "stale" || draftChanged
        ? "stale"
        : state.promptPreviewStatus === "updating"
          ? "updating"
          : "ready";
  const statusLabel =
    state.promptPreviewStatus === "unavailable"
      ? "Preview unavailable"
      : state.promptPreviewStatus === "stale"
        ? "Showing last successful preview"
        : draftChanged
          ? "Draft changed · waiting to update"
          : state.promptPreviewStatus === "updating"
            ? state.promptPreviewSource === "sent"
              ? "Preparing sent-message snapshot"
              : "Updating…"
            : state.promptPreviewSource === "sent"
              ? "Sent-message snapshot"
              : state.promptPreviewStatus === "up_to_date"
                ? "Up to date"
                : "Preparing preview…";

  function handleAction(action: InspectorAction) {
    if (action === "parent") {
      actions.selectScope(activeDomainId, null);
      actions.setRightMode("settings");
      return;
    }
    if (action === "repositories") {
      actions.setRightMode("documents");
      return;
    }
    actions.setRightMode(action);
  }

  async function applyLayerControl(layer: PromptLayer, enabled: boolean, riskAcknowledged = false) {
    setChangingLayerKey(layer.key);
    const changed = await actions.setPromptLayerEnabled(layer.key, enabled, riskAcknowledged, draft);
    setChangingLayerKey(null);
    if (changed) {
      setAdvancedLayer(null);
      setAdvancedAcknowledged(false);
    }
  }

  function requestLayerControl(layer: PromptLayer, enabled: boolean) {
    if (layer.control === "advanced" && !enabled) {
      setAdvancedLayer(layer);
      setAdvancedAcknowledged(false);
      return;
    }
    void applyLayerControl(layer, enabled);
  }

  return (
    <>
      <p className="panel-intro">
        {preservingSentSnapshot
          ? "This is the frozen rules, scope, knowledge, and conversation snapshot used for the message you just sent."
          : "This explains the rules, scope, knowledge, and conversation context the model will receive if you send your current draft. Expand an implemented background layer to include or exclude it for this scope."}
      </p>
      <div className="inspector-summary" aria-label="Prompt layer summary">
        <span className={`inspector-ready ${statusClass}`} aria-live="polite">{statusLabel}</span>
        <span>{includedCount} included</span>
        <span>{notIncludedCount} not included</span>
        <span>{plannedCount} planned</span>
      </div>
      {state.promptPreviewError && (
        <p className="inspector-notice" role="status">{state.promptPreviewError}</p>
      )}
      {advancedLayer && (
        <section className="prompt-layer-warning" role="alert">
          <strong>Turn off {layerLabel(advancedLayer)}?</strong>
          <p>
            This removes model-level safety or operating instructions for this scope. The model may follow
            untrusted instructions, ignore scope boundaries, or answer less reliably.
          </p>
          <p>
            Authentication, ownership checks, retrieval isolation, archive validation, and filesystem restrictions
            remain enforced by the framework code.
          </p>
          <label>
            <input
              type="checkbox"
              checked={advancedAcknowledged}
              onChange={(event) => setAdvancedAcknowledged(event.target.checked)}
            />
            I understand this changes the next model input for this scope.
          </label>
          <div>
            <button
              className="btn-text"
              type="button"
              onClick={() => {
                setAdvancedLayer(null);
                setAdvancedAcknowledged(false);
              }}
            >
              Cancel
            </button>
            <button
              className="btn-primary danger"
              type="button"
              disabled={!advancedAcknowledged || changingLayerKey !== null || state.streaming}
              onClick={() => void applyLayerControl(advancedLayer, false, true)}
            >
              Turn off for this scope
            </button>
          </div>
        </section>
      )}
      {state.promptLayers.length === 0 && state.promptPreviewStatus !== "unavailable" && (
        <p className="empty-state">The first preview is being assembled…</p>
      )}
      {INSPECTOR_GROUPS.map((group) => {
        const groupViews = views.filter((view) => view.group === group.id);
        if (groupViews.length === 0) return null;
        const groupIncluded = groupViews.filter((view) => view.layer.applied).length;
        return (
          <details className="inspector-group" key={group.id} open={openGroupId === group.id}>
            <summary
              className="inspector-group-h"
              onClick={(event) => {
                event.preventDefault();
                setOpenGroupId((current) => current === group.id ? null : group.id);
              }}
            >
              <span>
                <strong>{group.label}</strong>
                <small>{group.description}</small>
              </span>
              <span>{groupIncluded}/{groupViews.length} included</span>
            </summary>
            <div className="inspector-group-body">
              {groupViews.map((view) => (
                <Layer
                  key={view.layer.key}
                  view={view}
                  onAction={handleAction}
                  onToggle={requestLayerControl}
                  changing={changingLayerKey === view.layer.key}
                  generationActive={state.streaming}
                />
              ))}
            </div>
          </details>
        );
      })}
    </>
  );
}

function statusLabel(status: DocumentStatus): string {
  if (status === "ready") return "ready";
  if (status === "failed") return "failed";
  return "processing…";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function snapshotLabel(repository: CodeRepositoryInfo): string {
  return repository.revisionLabel || `snapshot ${repository.contentHash.slice(0, 12)}`;
}

function DocumentsPanel({ ws }: { ws: Workspace }) {
  const { activeScope, state, actions } = ws;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const repositoryInputRef = useRef<HTMLInputElement>(null);
  const replacementInputRef = useRef<HTMLInputElement>(null);
  const previewRequestRef = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [exportingDocumentId, setExportingDocumentId] = useState<string | null>(null);
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewTitle, setPreviewTitle] = useState("");
  const [organizerModelTag, setOrganizerModelTag] = useState("");
  const [organizationPreview, setOrganizationPreview] = useState<DocumentOrganizationPreview | null>(null);
  const [organizing, setOrganizing] = useState(false);
  const [applyingOrganization, setApplyingOrganization] = useState(false);
  const [organizationReviewed, setOrganizationReviewed] = useState(false);
  const [repositoryUploading, setRepositoryUploading] = useState(false);
  const [replacementTargetId, setReplacementTargetId] = useState<string | null>(null);

  useEffect(() => {
    setOrganizationPreview(null);
    setOrganizationReviewed(false);
  }, [activeScope?.id]);

  if (!activeScope) {
    return <p className="empty-state">Select a domain or sub-domain to manage its documents.</p>;
  }

  function pickFile() {
    fileInputRef.current?.click();
  }

  async function uploadFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await actions.uploadDocument(file);
      }
    } finally {
      setUploading(false);
    }
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    await uploadFiles(files);
    e.target.value = "";
  }

  async function exportMarkdown(document: DocumentInfo) {
    if (exportingDocumentId) return;
    setExportingDocumentId(document.id);
    try {
      await actions.downloadDocumentMarkdown(document.id, document.filename);
    } finally {
      setExportingDocumentId(null);
    }
  }

  async function convertMarkdown(document: DocumentInfo) {
    if (exportingDocumentId) return;
    setExportingDocumentId(document.id);
    try {
      await actions.createDocumentMarkdown(document.id);
    } finally {
      setExportingDocumentId(null);
    }
  }

  async function openPreview(
    document: DocumentInfo,
    variant: "source" | "markdown" = "source",
    ownerScopeId?: string
  ) {
    const requestId = ++previewRequestRef.current;
    setPreviewTitle(variant === "markdown" ? document.markdownFilename ?? document.filename : document.filename);
    setPreview(null);
    setPreviewLoading(true);
    const result = await actions.previewDocument(document.id, variant, ownerScopeId);
    if (requestId !== previewRequestRef.current) return;
    setPreview(result);
    setPreviewLoading(false);
  }

  function closePreview() {
    previewRequestRef.current += 1;
    setPreview(null);
    setPreviewLoading(false);
  }

  async function generateOrganizationPreview() {
    if (organizing || state.documents.length === 0) return;
    setOrganizing(true);
    setOrganizationReviewed(false);
    try {
      const preview = await actions.previewDocumentOrganization(organizerModelTag || null);
      setOrganizationPreview(preview);
    } finally {
      setOrganizing(false);
    }
  }

  function updateOrganizationSuggestion(
    documentId: string,
    patch: Partial<DocumentOrganizationSuggestion>
  ) {
    setOrganizationPreview((current) =>
      current
        ? {
            ...current,
            suggestions: current.suggestions.map((suggestion) =>
              suggestion.documentId === documentId ? { ...suggestion, ...patch } : suggestion
            ),
          }
        : current
    );
    setOrganizationReviewed(false);
  }

  async function applyOrganization() {
    if (!organizationPreview || !organizationReviewed || applyingOrganization) return;
    setApplyingOrganization(true);
    try {
      const applied = await actions.applyDocumentOrganization(
        organizationPreview.documentSetHash,
        organizationPreview.suggestions
      );
      if (applied) {
        setOrganizationPreview(null);
        setOrganizationReviewed(false);
      }
    } finally {
      setApplyingOrganization(false);
    }
  }

  async function onRepositoryChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      actions.pushToast("Repository snapshots must be .zip files.");
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      actions.pushToast("Repository snapshots cannot exceed 100 MiB compressed.");
      return;
    }
    const defaultName = file.name.replace(/\.zip$/i, "") || "Repository";
    const name = window.prompt("Repository display name", defaultName)?.trim();
    if (!name) return;
    const revision = window.prompt(
      "Optional revision label (for example, release-2026-08). This is a label, not a verified Git commit.",
      ""
    );
    if (revision === null) return;
    const confirmed = window.confirm(
      `Import repository snapshot?\n\nScope: ${ws.scopePath}\nArchive: ${file.name}\nCompressed size: ${formatFileSize(file.size)}\nName: ${name}`
    );
    if (!confirmed) return;
    setRepositoryUploading(true);
    try {
      await actions.uploadRepository(file, name, revision.trim() || undefined);
    } finally {
      setRepositoryUploading(false);
    }
  }

  function chooseReplacement(repositoryId: string) {
    setReplacementTargetId(repositoryId);
    replacementInputRef.current?.click();
  }

  async function onReplacementChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    const target = state.repositories.find((item) => item.id === replacementTargetId);
    setReplacementTargetId(null);
    if (!file || !target) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      actions.pushToast("Repository snapshots must be .zip files.");
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      actions.pushToast("Repository snapshots cannot exceed 100 MiB compressed.");
      return;
    }
    const revision = window.prompt(
      "Optional revision label. This is a label, not a verified Git commit.",
      target.revisionLabel ?? ""
    );
    if (revision === null) return;
    const confirmed = window.confirm(
      `Replace ${target.name}?\n\nScope: ${ws.scopePath}\nArchive: ${file.name}\nCompressed size: ${formatFileSize(file.size)}\n\nThe current snapshot stays active unless validation and indexing succeed.`
    );
    if (!confirmed) return;
    setRepositoryUploading(true);
    try {
      await actions.replaceRepository(target.id, file, revision.trim() || undefined);
    } finally {
      setRepositoryUploading(false);
    }
  }

  async function confirmRepositoryDelete(repository: CodeRepositoryInfo) {
    const typed = window.prompt(
      `Permanently delete ${repository.name} and its local files, index, grants, and retrieval records?\n\nType the repository name to confirm:`,
      ""
    );
    if (typed !== repository.name) {
      if (typed !== null) actions.pushToast("Repository name did not match. Nothing was deleted.");
      return;
    }
    await actions.deleteRepository(repository.id);
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragging(true);
  }

  function onDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
  }

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    await uploadFiles(e.dataTransfer.files);
  }

  const documentGroups = Object.entries(
    state.documents.reduce<Record<string, DocumentInfo[]>>((groups, document) => {
      const folder = document.folderPath || "";
      groups[folder] = [...(groups[folder] ?? []), document];
      return groups;
    }, {})
  ).sort(([folderA], [folderB]) => {
    if (!folderA) return 1;
    if (!folderB) return -1;
    return folderA.localeCompare(folderB);
  });

  return (
    <>
      <PanelSection
        id="documents-files"
        title="Document files"
        description="Upload and manage local reference files"
        meta={`${state.documents.length} local${state.inheritedDocuments.length ? ` · ${state.inheritedDocuments.length} shared` : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".md,.markdown,.txt,.pdf"
          multiple
          style={{ display: "none" }}
          onChange={onFileChosen}
        />
        <div
          className={`dropzone${dragging ? " active" : ""}`}
          onClick={pickFile}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              pickFile();
            }
          }}
        >
          {uploading ? "Uploading…" : "Drop files here, or click to upload"}
          <span className="dropzone-hint">.md, .txt, .pdf</span>
        </div>
        <p className="pdf-export-hint">
          Every file can be viewed here. For a text-based PDF, choose <b>Convert</b> to keep a Markdown copy in the
          same virtual folder. Scanned image-only PDFs require OCR first.
        </p>

        {state.documentsLoading && state.documents.length === 0 ? (
          <p className="empty-state">Loading documents…</p>
        ) : state.documents.length === 0 ? (
          <p className="empty-state">No documents in this scope yet.</p>
        ) : (
          documentGroups.map(([folder, documents]) => (
            <section className="doc-folder-group" key={folder || "unsorted"}>
              <div className="doc-folder-heading">{folder || "Unsorted"}</div>
              {documents.map((doc) => (
                <div className="doc-file-stack" key={doc.id}>
                <div className="doc-row" title={doc.error ?? undefined}>
                  <span className="doc-name-block">
                    <span className="n">{doc.filename}</span>
                    {doc.tags.length > 0 && <small>{doc.tags.join(" · ")}</small>}
                  </span>
                  <span className="stub-badge">
                    {statusLabel(doc.status)}
                    {doc.status === "ready" ? ` · ${doc.chunkCount} chunks` : ""}
                  </span>
                  <span className="doc-actions">
                    <button
                      className="doc-export"
                      onClick={() => openPreview(doc)}
                      type="button"
                      title="View document"
                      aria-label={`View ${doc.filename}`}
                    >
                      View
                    </button>
                    {doc.sourceType === "pdf" && (
                      <button
                        className="doc-export"
                        disabled={exportingDocumentId !== null}
                        onClick={() => convertMarkdown(doc)}
                        type="button"
                        title={doc.markdownAvailable ? "Rebuild the stored Markdown copy" : "Convert and store in this folder"}
                        aria-label={`Convert ${doc.filename} to Markdown`}
                      >
                        {exportingDocumentId === doc.id ? "…" : doc.markdownAvailable ? "Rebuild" : "Convert"}
                      </button>
                    )}
                    <button
                      className="doc-remove"
                      onClick={() => actions.deleteDocument(doc.id)}
                      type="button"
                      title="Delete document"
                      aria-label={`Delete ${doc.filename}`}
                    >
                      ×
                    </button>
                  </span>
                </div>
                {doc.markdownAvailable && (
                  <div className="doc-row doc-derived-row">
                    <span className="doc-name-block">
                      <span className="n">{doc.markdownFilename}</span>
                      <small>Markdown copy · same folder</small>
                    </span>
                    <span className="doc-actions">
                      <button className="doc-export" type="button" onClick={() => openPreview(doc, "markdown")}>View</button>
                      <button className="doc-export" type="button" onClick={() => exportMarkdown(doc)}>Download</button>
                    </span>
                  </div>
                )}
                </div>
              ))}
            </section>
          ))
        )}

        {state.inheritedDocuments.length > 0 && (
          <>
            <div className="section-title">Inherited from parent / shared scopes</div>
            <div className="settings-hint">Read-only here — edit these from their owning scope.</div>
            {state.inheritedDocuments.map((doc: InheritedDocumentInfo) => (
              <div className="doc-row" key={doc.id}>
                <span className="n">
                  {doc.filename} <span className="stub-badge">{doc.scopeName}</span>
                </span>
                <span className="stub-badge">{statusLabel(doc.status)}</span>
                <button
                  className="doc-export"
                  type="button"
                  onClick={() => openPreview(doc, "source", doc.scopeId)}
                  aria-label={`View ${doc.filename}`}
                >
                  View
                </button>
              </div>
            ))}
          </>
        )}
      </PanelSection>

      <PanelSection
        id="documents-organizer"
        title="AI document organizer"
        description="Preview virtual folders and tags before applying"
        meta={state.documents.length ? `${state.documents.length} local` : undefined}
      >
        <p className="panel-intro">
          A local Ollama model reviews filenames and short indexed excerpts, then proposes virtual folders and tags.
          It does not move or rename source files. Review and edit every suggestion before applying it.
        </p>
        <div className="settings-field">
          <label htmlFor="organizer-model">Organizer model</label>
          <select
            id="organizer-model"
            value={organizerModelTag}
            onChange={(event) => {
              setOrganizerModelTag(event.target.value);
              setOrganizationPreview(null);
              setOrganizationReviewed(false);
            }}
            disabled={organizing || applyingOrganization}
          >
            <option value="">Recommended automatically (largest installed)</option>
            {state.models.filter((model) => !model.tag.toLowerCase().includes("embed")).map((model) => (
              <option key={model.tag} value={model.tag}>
                {model.name} ({model.tag})
              </option>
            ))}
          </select>
          <div className="settings-hint">
            Only the filename, current metadata, and a short indexed excerpt are sent to this local model.
          </div>
        </div>
        <button
          className="btn-outline organizer-generate"
          type="button"
          onClick={generateOrganizationPreview}
          disabled={organizing || applyingOrganization || state.documents.length === 0}
        >
          {organizing ? "Generating preview…" : "Generate organization preview"}
        </button>

        {organizationPreview && (
          <div className="organizer-preview">
            <div className="organizer-preview-heading">
              <strong>Review every suggestion</strong>
              <span>Model: {organizationPreview.modelTag}</span>
            </div>
            {organizationPreview.warnings.map((warning) => (
              <p className="organizer-warning" key={warning}>{warning}</p>
            ))}
            {organizationPreview.suggestions.map((suggestion) => (
              <article className="organizer-suggestion" key={suggestion.documentId}>
                <strong title={suggestion.filename}>{suggestion.filename}</strong>
                <label>
                  Virtual folder
                  <input
                    type="text"
                    value={suggestion.folderPath}
                    onChange={(event) =>
                      updateOrganizationSuggestion(suggestion.documentId, { folderPath: event.target.value })
                    }
                    placeholder="For example: Finance/Contracts"
                    maxLength={243}
                  />
                </label>
                <label>
                  Tags, separated by commas
                  <input
                    type="text"
                    value={suggestion.tags.join(", ")}
                    onChange={(event) =>
                      updateOrganizationSuggestion(suggestion.documentId, {
                        tags: event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean),
                      })
                    }
                    placeholder="contract, client, 2026"
                  />
                </label>
                <small>{suggestion.reason}</small>
              </article>
            ))}
            <label className="organizer-consent">
              <input
                type="checkbox"
                checked={organizationReviewed}
                onChange={(event) => setOrganizationReviewed(event.target.checked)}
              />
              I reviewed the proposed folders and tags for every document.
            </label>
            <button
              className="btn-primary"
              type="button"
              onClick={applyOrganization}
              disabled={!organizationReviewed || applyingOrganization}
            >
              {applyingOrganization ? "Applying…" : "Apply organization"}
            </button>
          </div>
        )}
      </PanelSection>

      <PanelSection
        id="documents-repositories"
        title="Code repository snapshots"
        description="Import searchable, read-only .zip snapshots"
        meta={`${state.repositories.length} imported`}
      >
        <p className="panel-intro">
          Upload a <b>.zip copy</b> of a code repository so the assistant can search and reference its files in this
          scope. This creates a read-only snapshot—it does not connect to GitHub, run the code, or automatically receive
          future changes. To update it, replace the snapshot with a newer .zip. Search stays local, and repository access
          is never inherited by a parent, child, or sibling scope.
        </p>
        <input
          ref={repositoryInputRef}
          type="file"
          accept=".zip,application/zip"
          style={{ display: "none" }}
          onChange={onRepositoryChosen}
        />
        <input
          ref={replacementInputRef}
          type="file"
          accept=".zip,application/zip"
          style={{ display: "none" }}
          onChange={onReplacementChosen}
        />
        <button
          className="btn-outline repository-import"
          type="button"
          onClick={() => repositoryInputRef.current?.click()}
          disabled={repositoryUploading}
        >
          {repositoryUploading ? "Processing repository…" : "Import repository snapshot (.zip)"}
        </button>
        <p className="repository-warning">
          Files are screened for common secrets before indexing. Automated detection reduces risk but cannot guarantee
          that a repository contains no sensitive data—review the archive before importing it.
        </p>

        {state.repositoriesLoading && state.repositories.length === 0 ? (
          <p className="empty-state">Loading repository snapshots…</p>
        ) : state.repositories.length === 0 ? (
          <p className="empty-state">No repository snapshots are available to this scope.</p>
        ) : (
          state.repositories.map((repository) => (
            <article className="repository-row" key={repository.id}>
              <div className="repository-row-heading">
                <span className="repository-name">{repository.name}</span>
                <span className={`stub-badge repository-status ${repository.status}`}>{repository.status}</span>
              </div>
              <div className="repository-meta">
                <span>{snapshotLabel(repository)}</span>
                <span>scope {ws.scopePath}</span>
                <span>{repository.fileCount} accepted</span>
                <span>{repository.skippedFileCount} skipped</span>
                <span>{repository.securityExcludedCount} security-excluded</span>
                <span>{repository.chunkCount} searchable chunks</span>
              </div>
              {repository.error && <p className="repository-error">{repository.error}</p>}
              {repository.exclusions.length > 0 && (
                <details className="repository-exclusions">
                  <summary>Review {repository.exclusions.length} excluded file(s)</summary>
                  <ul>
                    {repository.exclusions.map((exclusion, index) => (
                      <li key={`${exclusion.path}-${index}`}>
                        <code>{exclusion.path}</code>
                        <span>{exclusion.reason}{exclusion.security ? " · security" : ""}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <div className="repository-actions">
                <button
                  className="btn-outline"
                  type="button"
                  onClick={() => chooseReplacement(repository.id)}
                  disabled={repositoryUploading || repository.status !== "ready"}
                  aria-label={`Replace snapshot for ${repository.name}`}
                >
                  Replace / reindex
                </button>
                <button
                  className="btn-outline danger"
                  type="button"
                  onClick={() => confirmRepositoryDelete(repository)}
                  disabled={repositoryUploading}
                  aria-label={`Delete repository ${repository.name}`}
                >
                  Delete
                </button>
              </div>
            </article>
          ))
        )}
      </PanelSection>

      <div
        className={`backdrop${previewLoading || preview ? " open" : ""}`}
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) {
            closePreview();
          }
        }}
      >
        <section className="modal document-preview-modal" role="dialog" aria-modal="true" aria-label={`View ${previewTitle}`}>
          <div className="document-preview-heading">
            <div>
              <h2>{previewTitle}</h2>
              <div className="sub">
                {previewLoading ? "Opening document…" : preview?.truncated
                  ? `Showing the first ${preview.content.length.toLocaleString()} of ${preview.characterCount.toLocaleString()} characters`
                  : `${preview?.characterCount.toLocaleString() ?? 0} characters`}
              </div>
            </div>
            <button className="doc-remove" type="button" onClick={closePreview} aria-label="Close document viewer">×</button>
          </div>
          <div className="document-preview-body">
            {previewLoading ? (
              <p className="empty-state">Preparing a safe text preview…</p>
            ) : preview?.format === "markdown" ? (
              <div className="markdown-message"><MarkdownMessage content={preview.content} /></div>
            ) : (
              <pre>{preview?.content}</pre>
            )}
          </div>
          <div className="modal-actions">
            <button className="btn-primary" type="button" onClick={closePreview}>Close</button>
          </div>
        </section>
      </div>
    </>
  );
}

function MemoryRow({
  memory,
  onSave,
  onDelete,
}: {
  memory: MemoryInfo;
  onSave: (content: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(memory.content);

  if (editing) {
    return (
      <div className="memory-row editing">
        <textarea rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
        <div className="memory-row-actions">
          <button
            className="btn-outline"
            type="button"
            onClick={() => {
              setEditing(false);
              setDraft(memory.content);
            }}
          >
            Cancel
          </button>
          <button
            className="btn-primary"
            type="button"
            onClick={() => {
              onSave(draft);
              setEditing(false);
            }}
          >
            Save
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="memory-row">
      <p
        className="memory-content"
        onClick={() => setEditing(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setEditing(true);
          }
        }}
        role="button"
        tabIndex={0}
        title="Edit memory"
      >
        {memory.content}
      </p>
      <div className="memory-row-actions">
        <span className="settings-hint">{memory.conversationId ? "saved from chat" : "manual"}</span>
        <button className="doc-remove" onClick={onDelete} type="button" title="Delete memory" aria-label="Delete memory">
          ×
        </button>
      </div>
    </div>
  );
}

function MemoryPanel({ ws }: { ws: Workspace }) {
  const { activeScope, state, actions } = ws;
  const [draft, setDraft] = useState("");

  if (!activeScope) {
    return <p className="empty-state">Select a domain or sub-domain to manage its memory.</p>;
  }

  async function save() {
    if (!draft.trim()) return;
    await actions.createMemory(draft);
    setDraft("");
  }

  return (
    <>
      <PanelSection
        id="memory-add"
        title="Add a memory"
        description="Save a fact, decision, or note for this scope"
      >
        <div className="settings-field">
          <textarea
            rows={3}
            placeholder="A fact, decision, or note this scope should always remember…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </div>
        <button className="btn-outline" onClick={save} type="button" disabled={!draft.trim()}>
          Save memory
        </button>
      </PanelSection>

      <PanelSection
        id="memory-saved"
        title="Saved memories"
        description="Review local and inherited memories"
        meta={`${state.memories.length} local${state.inheritedMemories.length ? ` · ${state.inheritedMemories.length} shared` : ""}`}
      >
        {state.memoriesLoading && state.memories.length === 0 ? (
          <p className="empty-state">Loading memories…</p>
        ) : state.memories.length === 0 ? (
          <p className="empty-state">No memories saved in this scope yet.</p>
        ) : (
          state.memories.map((m: MemoryInfo) => (
            <MemoryRow
              key={m.id}
              memory={m}
              onSave={(content) => actions.updateMemory(m.id, content)}
              onDelete={() => actions.deleteMemory(m.id)}
            />
          ))
        )}

        {state.inheritedMemories.length > 0 && (
          <>
            <div className="section-title">Inherited from parent / shared scopes</div>
            <div className="settings-hint">Read-only here — edit these from their owning scope.</div>
            {state.inheritedMemories.map((m: InheritedMemoryInfo) => (
              <div className="memory-row" key={m.id}>
                <p className="memory-content">
                  {m.content} <span className="stub-badge">{m.scopeName}</span>
                </p>
              </div>
            ))}
          </>
        )}
      </PanelSection>
    </>
  );
}

const MODEL_PRESETS = {
  precise: { temperature: 0.2, topP: 0.8, topK: 20, repeatPenalty: 1.1 },
  balanced: { temperature: 0.7, topP: 0.9, topK: 40, repeatPenalty: 1.1 },
  creative: { temperature: 1, topP: 0.95, topK: 60, repeatPenalty: 1.05 },
} as const;

function DomainModelSettingsEditor({ ws, idPrefix = "settings" }: { ws: Workspace; idPrefix?: string }) {
  const { state, actions } = ws;
  const [draft, setDraft] = useState<DomainModelSettings | null>(state.domainModelSettings);
  const [saving, setSaving] = useState(false);

  useEffect(() => setDraft(state.domainModelSettings), [state.domainModelSettings]);
  if (!draft) return <p className="empty-state">Loading this domain&apos;s model settings…</p>;

  const contextChoices = Array.from(new Set([
    4096, 8192, 16384, 32768, 65536,
    draft.contextLength,
    draft.recommendedContextLength,
  ])).filter((value) => value <= (draft.nativeContextLength ?? 262144)).sort((a, b) => a - b);
  const answerChoices = Array.from(new Set([
    512, 1024, 2048, 4096, draft.maxOutputTokens,
  ])).filter((value) => value <= draft.contextLength / 2).sort((a, b) => a - b);

  async function save() {
    setSaving(true);
    await actions.saveDomainModelSettings(draft!);
    setSaving(false);
  }

  function useSuggestedSettings() {
    const contextLength = draft!.recommendedContextLength;
    setDraft({
      ...draft!,
      ...MODEL_PRESETS.balanced,
      contextLength,
      maxOutputTokens: Math.min(2048, contextLength / 2),
    });
  }

  return (
    <>
      <div className="settings-field">
        <label>Model</label>
        <select value={draft.modelTag} onChange={(event) => setDraft({ ...draft, modelTag: event.target.value })}>
          {state.models.map((model) => <option value={model.tag} key={model.tag}>{model.name}</option>)}
        </select>
        <div className="settings-hint">Saved only for this domain or sub-domain.</div>
      </div>
      <div className="settings-field">
        <label>Context window for each request</label>
        <div className="model-token-options" role="group" aria-label="Request context">
          {contextChoices.map((value) => (
            <button
              type="button"
              className={value === draft.contextLength ? "on" : ""}
              aria-pressed={value === draft.contextLength}
              onClick={() => setDraft({ ...draft, contextLength: value, maxOutputTokens: Math.min(draft.maxOutputTokens, value / 2) })}
              key={value}
            >
              {(value / 1024).toFixed(value % 1024 === 0 ? 0 : 1)}K
              {value === draft.recommendedContextLength && <small>Suggested</small>}
            </button>
          ))}
        </div>
        <button
          className="btn-outline model-auto-button"
          type="button"
          onClick={useSuggestedSettings}
        >
          {draft.detectedAllocatedContextLength ? "Use hardware-detected settings" : "Use safe suggested settings"} · {(draft.recommendedContextLength / 1024).toFixed(0)}K
        </button>
        <div className="settings-hint">{draft.recommendationBasis}</div>
      </div>
      <div className="settings-field">
        <label>Maximum answer length</label>
        <div className="model-token-options answer" role="group" aria-label="Maximum answer length">
          {answerChoices.map((value) => (
            <button
              type="button"
              className={value === draft.maxOutputTokens ? "on" : ""}
              aria-pressed={value === draft.maxOutputTokens}
              onClick={() => setDraft({ ...draft, maxOutputTokens: value })}
              key={value}
            >
              {value === 512 ? "Short" : value === 1024 ? "Standard" : value === 2048 ? "Long" : value === 4096 ? "Very long" : value.toLocaleString()}
              <small>{value.toLocaleString()}</small>
            </button>
          ))}
        </div>
        <div className="settings-hint">The framework reserves this space and drops the oldest chat turns first when a conversation grows.</div>
      </div>
      <div className="settings-field">
        <label>Response style</label>
        <div className="seg">
          {Object.entries(MODEL_PRESETS).map(([name, values]) => (
            <button
              type="button"
              className={Object.entries(values).every(([key, value]) => draft[key as keyof DomainModelSettings] === value) ? "on" : ""}
              aria-pressed={Object.entries(values).every(([key, value]) => draft[key as keyof DomainModelSettings] === value)}
              key={name}
              onClick={() => setDraft({ ...draft, ...values })}
            >
              {name.charAt(0).toUpperCase() + name.slice(1)}
            </button>
          ))}
        </div>
        <div className="settings-hint">Precise is best for facts and summaries. Balanced fits most work. Creative allows more variation.</div>
      </div>
      <div className="settings-field model-temperature-control">
        <label htmlFor={`${idPrefix}-temperature`}>Creativity (temperature) · {draft.temperature.toFixed(2)}</label>
        <input id={`${idPrefix}-temperature`} type="range" min="0" max="2" step="0.05" value={draft.temperature} onChange={(e) => setDraft({ ...draft, temperature: Number(e.target.value) })} />
        <div className="model-temperature-scale"><span>Consistent</span><span>Balanced</span><span>Varied</span></div>
        <div className="settings-hint">This changes response variation. It does not increase the context that fits in memory.</div>
      </div>
      <details className="model-advanced-settings">
        <summary>More response controls</summary>
        <div className="settings-field"><label>Top P · {draft.topP.toFixed(2)}</label><input type="range" min="0.05" max="1" step="0.05" value={draft.topP} onChange={(e) => setDraft({ ...draft, topP: Number(e.target.value) })} /></div>
        <div className="settings-field"><label>Top K · {draft.topK}</label><input type="range" min="1" max="100" step="1" value={draft.topK} onChange={(e) => setDraft({ ...draft, topK: Number(e.target.value) })} /></div>
        <div className="settings-field"><label>Repeat penalty · {draft.repeatPenalty.toFixed(2)}</label><input type="range" min="0.8" max="2" step="0.05" value={draft.repeatPenalty} onChange={(e) => setDraft({ ...draft, repeatPenalty: Number(e.target.value) })} /></div>
      </details>
      <button className="btn-primary model-settings-save" type="button" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save for this domain"}</button>
    </>
  );
}

function Settings({ ws, onDeleteScope }: { ws: Workspace; onDeleteScope: () => void }) {
  const { activeScope, activeSubdomain, actions } = ws;
  const isSub = !!activeSubdomain;

  if (!activeScope) {
    return <p className="empty-state">Select a domain or sub-domain to edit its settings.</p>;
  }

  return (
    <>
      <PanelSection
        id="settings-identity"
        title="Identity and instructions"
        description="Name this scope and define how its model should behave"
      >
        <div className="settings-field">
          <label>Name</label>
          <input type="text" value={activeScope.name} onChange={(e) => actions.updateScopeField("name", e.target.value)} />
        </div>
        <div className="settings-field">
          <label>Description</label>
          <textarea rows={2} value={activeScope.description} onChange={(e) => actions.updateScopeField("description", e.target.value)} />
        </div>
        <div className="settings-field">
          <label>Scope prompt</label>
          <textarea rows={5} value={activeScope.prompt} onChange={(e) => actions.updateScopeField("prompt", e.target.value)} />
        </div>
      </PanelSection>

      <PanelSection
        id="settings-model"
        title="Domain model settings"
        description="Model, context, answer length, and response style"
        meta={ws.state.domainModelSettings ? `${Math.round(ws.state.domainModelSettings.contextLength / 1024)}K request` : undefined}
      >
        <DomainModelSettingsEditor ws={ws} />
      </PanelSection>

      <PanelSection
        id="settings-sharing"
        title="Context sharing"
        description="Control parent inheritance and sibling prompt sharing"
        meta={isSub ? (activeScope.inheritance === "private" ? "Private" : "Uses parent") : "Per sub-domain"}
      >
        {isSub ? (
          <div className="settings-field">
            <label>Parent context</label>
            <div className="seg">
              <button className={activeScope.inheritance === "private" ? "on" : ""} onClick={() => actions.setInheritance("private")} type="button">
                Private
              </button>
              <button className={activeScope.inheritance === "inherited" ? "on" : ""} onClick={() => actions.setInheritance("inherited")} type="button">
                Use parent context
              </button>
            </div>
            <div className="settings-hint">
              Private uses only this sub-domain&apos;s own context. Use parent context also includes its parent domain&apos;s prompt, documents, and memories. Conversation history is never inherited.
            </div>
          </div>
        ) : (
          <div className="settings-field">
            <label>Sub-domain privacy</label>
            <div className="settings-hint">
              Each sub-domain chooses whether to use this domain&apos;s prompt, documents, and memories. Conversation history always stays with its own conversation.
            </div>
          </div>
        )}

        {isSub && (
          <div className="settings-field">
            <label>Share with sibling sub-domains</label>
            <div className="seg">
              <button
                className={!activeScope.shareWithSiblings ? "on" : ""}
                onClick={() => actions.setShareWithSiblings(false)}
                type="button"
              >
                Off
              </button>
              <button
                className={activeScope.shareWithSiblings ? "on" : ""}
                onClick={() => actions.setShareWithSiblings(true)}
                type="button"
              >
                On
              </button>
            </div>
            <div className="settings-hint">
              Off by default. When on, this sub-domain&apos;s own prompt becomes visible to its
              siblings (other sub-domains under the same parent) as shared context — it does not
              let this sub-domain read siblings in return, and never shares conversation history,
              only the prompt.
            </div>
          </div>
        )}
      </PanelSection>

      <PanelSection
        id="settings-tools"
        title="Tools"
        description="See which tools are available in this scope"
        meta={`${TOOLS.filter((tool) => tool.status === "Active/local").length} active`}
      >
        {TOOLS.map((tool) => (
          <div className={`stub-row${tool.status === "Active/local" ? " active-tool" : ""}`} key={tool.name}>
            <span className="n">{tool.name}</span>
            <span className="stub-badge">{tool.status}</span>
          </div>
        ))}
      </PanelSection>

      <PanelSection
        id="settings-danger"
        title="Danger zone"
        description={`Archive, export, or permanently delete this ${isSub ? "sub-domain" : "domain"}`}
        tone="danger"
      >
        <div className="danger-zone">
          <div className="settings-hint">
            Delete permanently removes {isSub ? "this sub-domain and its data" : "this domain, its sub-domains, and their data"}. Archive and export are planned for a future version.
          </div>
          <div className="dz-row">
            <button className="btn-outline" type="button" disabled title="Planned for a future version">
              Archive · planned
            </button>
            <button className="btn-outline" type="button" disabled title="Planned for a future version">
              Export · planned
            </button>
            <button
              className="btn-outline danger"
              onClick={onDeleteScope}
              type="button"
              disabled={ws.state.streaming}
            >
              Delete
            </button>
          </div>
        </div>
      </PanelSection>
    </>
  );
}
