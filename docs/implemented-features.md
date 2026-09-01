# Implemented features

This is the public record of functionality currently present in the repository,
including its verification and distribution boundaries.

## Core framework

- FastAPI backend and Next.js frontend with PostgreSQL/pgvector persistence.
- One-owner authentication boundary and scope-owned data.
- User-created domains and one level of sub-domains.
- Rail dropdowns start closed. Selecting a domain expands its sub-domain list
  and collapses the other domain lists; only one domain is expanded at a time.
- The right rail uses the same accordion behavior: only one top-level choice
  is open in the current tab, and changing tabs or scopes starts with every
  choice closed. Prompt Inspector groups follow the same rule.
- Ordered prompt assembly with framework rules, model instructions, scope
  prompts, inherited/local memory, retrieved sources, conversation history,
  and the current user message.
- Explicit parent inheritance and sibling sharing rules calculated by the
  backend rather than selected by the model.
- Streaming chat, conversations, regeneration, citations, and locally stored
  generation feedback.
- Per-domain and per-sub-domain model settings for model choice, request
  context, maximum answer length, temperature, top P, top K, and repeat
  penalty. A simple suggested-settings action uses Ollama's loaded context
  evidence when available and a conservative value otherwise; Precise,
  Balanced, and Creative presets avoid requiring sampling expertise. See
  [Domain model settings](./domain-model-settings.md).
- Model Performance Optimizer places **Quick model tuning** before its advanced
  reports and benchmarks. Context and answer lengths are visible one-tap
  choices, temperature is a direct slider, and less common sampling controls
  remain in a compact advanced section. Hardware-impacting controls are
  distinguished from response-behaviour controls.
- Context-safe generation reserves answer space and removes the oldest chat
  turns first when the assembled request grows too large. An answer that
  reaches its configured limit is persisted and labelled as truncated instead
  of stopping without an explanation.
- Assistant responses render restrained Markdown for headings, emphasis, lists,
  links, tables, quotes, and code. Raw HTML is ignored and remote Markdown
  images are not loaded; user messages remain plain text.
- An optional latest-response learning-card tool that keeps the original answer
  unchanged and stores one short summary with exactly four simple cards. The
  backend enforces latest-message selection, structured output, and stale-result
  rejection. See [Learning cards](./learning-cards.md).
- Configurable light and dark interface themes.

## Local retrieval and memory

- Document upload, extraction, chunking, local Ollama embeddings, pgvector
  retrieval, citations, and retrieval audit records. Uploaded text-based PDFs
  can also be viewed in-app and extracted into page-labelled Markdown stored in
  the same scope and virtual folder, then viewed or downloaded;
  see [PDF to Markdown](./pdf-to-markdown.md).
- Local-model document organization with a recommended-or-explicit model
  choice, editable preview, virtual folder paths, tags, stale-preview
  protection, and explicit reviewed apply. Original files are not moved or
  renamed. See [AI Document Organizer](./document-organizer.md).
- Manually created or message-derived memories with source tracking, editing,
  deletion, and scope-aware inheritance.
- ZIP-based, read-only code repository snapshots with exact-scope grants,
  archive validation, dependency/generated/binary/credential exclusions,
  probable-secret screening, bounded hybrid search, path-and-line citations,
  atomic replacement, and deletion cleanup. See
  [Local Code Repository Search](./code-repository-search.md).

## Prompt Inspector

The **What the model sees** tab previews the same ordered prompt layers used by
generation. It reports whether each layer is included, lets the owner expand
the actual content, and stores per-scope enable/disable choices for implemented
background layers. Disabling a layer changes subsequent model input but does
not disable backend authentication, ownership, retrieval isolation, archive
validation, or filesystem controls. Advanced framework-rule and
model-instruction controls require an explicit warning acknowledgement.

## Model Performance Optimizer

The optional local optimizer reports the configured Ollama endpoint, model metadata,
runtime relationship, context, visible hardware/sensors, processor placement,
and evidence gaps. Its persistent, cancellable benchmark compares bounded
context candidates using built-in synthetic prompts and stores measurements in
PostgreSQL without using private conversations, documents, memories, or
repositories.

Completed comparisons report latency, generation rate, memory, context, power,
reliability, placement, Pareto tradeoffs, objective weights, confidence, and
deltas. A review workflow can apply a selected per-profile `num_ctx` value only
after revalidation, warning acknowledgement, and exact confirmation. Changes
are compare-and-set protected, verified, audited, and conditionally
rollbackable. The optimizer does not overclock hardware, expose a shell to the
model, restart Ollama, or apply server-global configuration.

The UI distinguishes the domain **request context**, Ollama's **loaded
allocation**, a model's **native context**, and the **profile context when
measured** in a historical benchmark. These values describe different layers
and are not presented as interchangeable.

## Setup and deployment

- The Welcome onboarding domain is seeded only once. If its owner deletes it
  (or deletes every domain), later container restarts preserve that choice.
- Docker Compose services for PostgreSQL/pgvector, backend, frontend, and an
  optional bundled Ollama service.
- Native, bundled, and remote Ollama connection modes.
- A standalone Tk graphical setup launcher for Windows, macOS, and Linux that
  performs preflight checks, offers explicit prerequisite installation paths,
  writes secret configuration atomically, starts selected services, pulls
  local models, selects the active model, and verifies backend, frontend, and
  backend-to-Ollama reachability.
- Cross-platform launcher tests and PyInstaller packaging in GitHub Actions,
  including a production-input integrity manifest. See
  [Local Setup Launcher](./setup-launcher.md).

## Secure remote API implementation preview

An optional Caddy HTTPS gateway and OpenAI-compatible `/v1` API are implemented
behind an Off-by-default backend mode. Remote devices use separate hash-stored,
revocable, domain-scoped keys; remote chat is stateless and retains framework
prompt, retrieval, memory, and per-domain tuning boundaries. A right-rail panel
shows mode and gateway state, manages keys, exposes the API address, downloads
the local CA certificate, and runs a safe gateway check.

Ollama keeps its native internal adapter. A second adapter supports models
served by a configured local OpenAI-compatible llama.cpp, LocalAI, or vLLM
endpoint and rejects public endpoints by default. See
[Secure remote API](./secure-remote-api.md) for the verified boundary and
remaining release checks. This preview is intentionally not advertised in the
main README until cross-platform LAN and Tailscale acceptance testing passes.

## Security properties verified in the repository

- Cross-domain and sibling isolation, explicit parent/child inheritance,
  unauthorized scope rejection, and retrieval access recalculated per request.
- Retrieved documents and repository excerpts are structurally marked as
  untrusted reference data.
- Destructive domain, conversation, document, memory, and repository paths
  have deletion/cascade coverage. See
  [Deletion and Storage Security](./deletion-security.md).
- The setup launcher uses fixed argument arrays without a shell, validates
  model tags and endpoints, bounds command duration/output, redacts secrets,
  preserves existing configuration by default, and does not expose the Docker
  socket or a host-command API.

## Verification boundary

The repository contains backend isolation, retrieval, deletion, prompt-layer,
optimizer, remote-API/runtime-adapter, and launcher tests plus a frontend
production build and Compose configuration checks. Some integration tests
require real PostgreSQL/pgvector and Ollama services. Public launcher artifacts are not yet signed or notarized;
clean-machine package installation and operating-system acceptance are manual
release checks. The project is not presented as hardened for multi-user or
public-internet deployment.
