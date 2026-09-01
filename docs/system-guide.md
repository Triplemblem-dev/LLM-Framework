# LLM Framework system guide

This guide describes the functionality currently implemented in the public
repository. It is a product and operations reference, not a development diary.

## What the framework is

LLM Framework is a self-hosted workspace for local large language models. It
organizes work into domains and sub-domains so that instructions, documents,
memories, conversations, repository snapshots, and model settings can remain
scoped to the topic that owns them.

The standard local deployment consists of:

- a Next.js browser interface;
- a FastAPI backend;
- PostgreSQL with pgvector for application data and vector search; and
- Ollama, either in Docker, installed natively, or available at a trusted
  remote endpoint.

The base Docker configuration is intended for a trusted computer or private
network. It is not a hardened multi-user or public-internet service.

## Workspace concepts

### Domains and sub-domains

A domain is a top-level workspace for a project, subject, client, or other
topic. A domain can contain one level of sub-domains for narrower areas. Each
scope has its own name, description, operating prompt, documents, memory,
conversations, repository grants, prompt-layer choices, and model settings.

Selecting a domain automatically reveals its sub-domains. Domain lists start
collapsed, only the selected domain is expanded, and only one accordion is
open per left- or right-rail section.

### Inheritance and sharing

A sub-domain can be private or can inherit its parent's prompt, documents, and
memories. Conversation history is never inherited. A sub-domain can optionally
share its own prompt with sibling sub-domains; this is off by default and does
not grant reciprocal access to sibling documents, memory, or conversations.

These relationships are calculated and enforced by the backend. The model
does not decide which scopes it may access.

### Conversations

Each conversation belongs to exactly one domain or sub-domain. Users can start
multiple conversations, return to earlier history, stream a response,
regenerate the latest assistant response, and delete a conversation through a
confirmation dialog. Citations and generation information are stored with the
corresponding messages.

Assistant messages render a restricted Markdown subset for readable headings,
lists, emphasis, links, tables, quotes, and code. Raw HTML is ignored and
remote Markdown images are not loaded. User messages remain plain text.

## Model selection and response controls

The framework lists models already available through the configured Ollama
endpoint. A framework model can be selected once, while every domain and
sub-domain can remember its own model and generation settings:

- request context length;
- maximum answer length;
- temperature;
- top P;
- top K; and
- repeat penalty.

Precise, Balanced, and Creative presets provide useful combinations without
requiring sampling expertise. Context and answer-length buttons and a visible
temperature slider provide quick adjustment. Less common sampling settings are
kept in the advanced section.

The interface deliberately separates four values that are often confused:

- **request context** is the window sent for the selected scope;
- **maximum answer length** is the space reserved for the response;
- **Ollama loaded allocation** is the current runtime allocation reported by
  Ollama; and
- **native context** is the model's reported maximum capability.

When a prompt becomes too large, the framework reserves response space and
removes the oldest conversation turns first. If a response reaches its answer
limit, it is saved and visibly marked as truncated rather than appearing to
stop without explanation.

## Prompt assembly and inspection

Every generation uses an ordered prompt assembled by the backend. Depending on
the selected scope and its controls, the prompt can contain:

1. framework security rules;
2. model operating instructions;
3. parent, local, and shared scope prompts;
4. inherited and local memory;
5. retrieved document excerpts;
6. retrieved code excerpts;
7. conversation history; and
8. the current user message.

The **What the model sees** panel previews these layers for the current draft.
Implemented background layers can be enabled or disabled per scope. Disabling
a prompt layer changes model input only; it does not disable authentication,
ownership checks, retrieval isolation, archive validation, or filesystem
restrictions. Turning off framework rules or model instructions requires an
explicit warning acknowledgement.

## Documents and local retrieval

Users can upload Markdown, plain text, and text-based PDF documents to a
domain or sub-domain. The backend extracts text, creates bounded chunks,
generates embeddings through the configured local Ollama embedding model, and
stores vectors in pgvector. Chat retrieval selects approved excerpts for the
active scope and records citations and retrieval evidence.

Documents have a **View** action. PDFs can also be converted to page-labelled
Markdown. The Markdown companion is stored inside the same scope and virtual
folder as its source, can be viewed or downloaded, and is linked to the source
instead of being indexed as duplicate content. Chat normally searches the
already extracted chunks, so it does not reread the PDF on every question.

### AI document organizer

The document organizer uses a selected local Ollama model to propose virtual
folders and tags from filenames and short indexed excerpts. It can recommend a
suitable installed non-embedding model or use a model chosen by the user.

Organization is a review-first workflow:

1. generate a preview;
2. inspect and edit every proposed path and tag;
3. acknowledge that the complete preview was reviewed; and
4. apply the organization.

Suggestions are checked for safe relative paths and stale document state.
Original files are not moved or renamed; the folder system is application
metadata used for browsing and retrieval.

## Code repository snapshot search

A ZIP snapshot of a code repository can be imported into one exact domain or
sub-domain. The snapshot is read-only and local. The system validates archive
paths and limits, excludes common dependencies, caches, generated files,
binaries, archives, credentials, keys, and probable secrets, then indexes
accepted source text for bounded hybrid search.

Retrieved code citations include repository name, relative path, and line
range. Repository access is not inherited by parents, children, or siblings.
Snapshots can be replaced atomically or permanently deleted.

The model receives no shell, Git operation, repository editing, package
installation, Docker socket, deployment, network, or arbitrary filesystem
tool. Automated secret screening reduces risk but cannot guarantee that an
archive is safe; users must review snapshots before uploading them.

## Memory

Memory stores facts or notes that should remain available beyond one chat.
Users can create memory manually, save it from a message, edit it, or delete
it. Memory is scope-aware and follows explicit parent inheritance rules.

A saved memory is an independent resource. Deleting its source conversation
does not delete the memory; its link to that conversation is cleared.

## Learning cards

After the latest assistant response finishes, **Make learning cards** asks the
active local model to condense it into one short summary and exactly four
simple cards. The original response is unchanged. Cards are stored with the
message and return when the conversation is reopened.

The backend accepts the action only for the latest eligible assistant message,
validates structured output, and rejects stale results if the conversation
changes while cards are being generated.

## Model Performance Optimizer

The optimizer has two roles. **Quick model tuning** exposes the same per-domain
model, context, answer length, style, and temperature controls used in scope
settings. Its suggested-settings action uses detected Ollama allocation when
available and a conservative current value otherwise. A benchmark is not
required to tune a domain.

The advanced optimizer can inspect:

- the configured Ollama endpoint and native/container/remote relationship;
- installed and loaded model metadata;
- processor placement as CPU, accelerator, split, or not yet observed;
- visible hardware, memory, sensors, and missing evidence; and
- connection failures with actionable diagnostics.

Optional context comparisons use bounded, built-in synthetic prompts. Runs are
stored locally, continue across page navigation, expose progress, and can be
cancelled. They do not use private conversations, documents, memories, or
repositories, and generated benchmark answers are discarded.

Reports separate latency, generation rate, memory, context, power,
reliability, and processor-placement evidence. They show trade-offs, objective
weights, confidence, deltas, failures, and a plain-language recommendation.
Results can be exported as a redacted Markdown report.

A context change is never applied by the benchmark itself. The review step
revalidates the model, endpoint, runtime evidence, native model limit, safety
ceiling, and current profile. Applying a change requires warning
acknowledgement and exact confirmation, uses compare-and-set protection, and
records an append-only local audit. Rollback is offered only while it cannot
overwrite a newer change.

## Deletion and data behavior

Domain, sub-domain, conversation, document, memory, repository, and optimizer
deletion routes resolve ownership in the backend. Browser IDs are never
treated as proof of access.

Deleting a top-level domain also deletes its sub-domains and associated
database records. Document storage is staged before the database transaction,
restored if the transaction fails, and removed after a successful commit.
Deletion is permanent and has no in-app undo; recovery requires an earlier
backup. Scope deletion therefore requires typed-name confirmation.

The Welcome domain is seeded only for a new owner with no recorded seed state.
Once it is deleted, restarting the containers does not recreate it.

## Authentication and security boundary

The current deployment uses one owner and an application access token. The
frontend sends that token as bearer authentication to protected backend
routes. Data ownership and exact-scope access are checked server-side.

Uploaded or retrieved content is treated as untrusted reference data. The
setup launcher uses fixed command argument arrays without a shell, validates
model tags and remote endpoints, bounds command time and captured output, and
redacts secrets. The Docker socket is not mounted into application services.

Keep `.env` private, do not publish application ports directly to the internet,
and use a reviewed private-network or reverse-proxy configuration for remote
access. See [Security policy](../SECURITY.md).

## Installation and runtime choices

The primary installation path is Git cloning plus Docker Compose. Docker runs
PostgreSQL and can run Ollama, so separate PostgreSQL or Ollama installation is
not required for the base CPU configuration. Native Ollama is optional and is
recommended on macOS for Metal acceleration. NVIDIA acceleration for Linux or
Windows/WSL2 uses the provided Compose overlay and requires the NVIDIA
container runtime.

An optional graphical setup launcher exists for Windows, macOS, and Linux. It
checks prerequisites, offers supported installation paths, creates secrets,
configures the selected Ollama mode, starts services, pulls models, selects the
active model, and verifies connectivity. Public Windows and macOS launcher
artifacts remain unsigned until maintainer-owned signing and notarization are
configured.

Runtime data lives in Docker volumes and the ignored local `.env`, not in Git.
Moving or recloning the source repository does not automatically move the
database, documents, or Ollama models.

## Repository layout

| Path | Purpose |
| --- | --- |
| `backend/` | FastAPI API, persistence, prompt assembly, retrieval, security rules, and tests |
| `frontend/` | Next.js interface and browser-side workspace state |
| `docs/` | Public product, setup, security, and implementation documentation |
| `benchmark/` | Standalone model-comparison prompts, runner, scoring, and sample results |
| `setup_launcher/` | Optional cross-platform graphical setup application and tests |
| `scripts/` | Native-host helper scripts |
| `docker-compose.yml` | Cross-platform base deployment |
| `docker-compose.gpu.yml` | Optional NVIDIA deployment overlay |

## Current limitations

- The application is designed for one trusted owner, not independent
  multi-user accounts.
- Direct public-internet exposure is not supported as a hardened deployment.
- PDF extraction targets text-based PDFs; scanned image PDFs require OCR that
  is not currently included.
- Archive and domain export controls shown in the interface are placeholders;
  permanent deletion is implemented, but in-app archive/export is not.
- Automated repository secret detection cannot replace manual review.
- Accelerator and power reporting depend on evidence exposed by the operating
  system, drivers, Ollama, and container runtime.
- Windows Authenticode signing and macOS signing/notarization are not yet
  configured for launcher releases.

## Focused references

- [Implemented features](./implemented-features.md)
- [Domain model settings](./domain-model-settings.md)
- [PDF to Markdown](./pdf-to-markdown.md)
- [AI document organizer](./document-organizer.md)
- [Local code repository search](./code-repository-search.md)
- [Learning cards](./learning-cards.md)
- [Deletion and storage security](./deletion-security.md)
- [Download and install](./download-and-install.md)
- [Local setup launcher](./setup-launcher.md)
