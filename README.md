# LLM Framework

A self-hosted framework for running local large language models
across user-defined **domains** and **sub-domains** — isolated,
scoped workspaces that each specialize one shared model through
prompts, retrieved documents, and memory, without mixing context
between them.

Not tied to one model, one profession, or one fixed set of
assistants: you pick the model (via [Ollama](https://ollama.com)),
then create domains for whatever you're actually working on. See the
[implemented-features record](./docs/implemented-features.md) for the public
summary of what is currently included and verified.

**Status**: personal project, under active development. The core
framework (domains, sub-domains, inheritance/sharing, document and local
code-repository search, memory, scoped tool permissions, isolation testing) is built and tested — see
`docs/` for current implementation and verification records. Not yet hardened for multi-user
or public-internet deployment.

## Quick start (Git clone + Docker Compose)

The supported installation path is to clone this GitHub repository and run the
framework with Docker Compose. Complete every prerequisite below before
starting the framework.

### 1. Install Git and clone the repository

Install [Git](https://git-scm.com/downloads/) for the computer, then verify it:

```bash
git --version
```

Choose where the project should live, open a terminal there, and run:

```bash
git clone https://github.com/Triplemblem-dev/LLM-Framework.git
cd LLM-Framework
```

GitHub also provides a [step-by-step cloning
guide](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository)
for Windows, macOS, and Linux.

### 2. Install and start Docker

- **Windows:** install [Docker Desktop for
  Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
  Docker Desktop will guide you through its WSL 2 requirement.
- **macOS:** install [Docker Desktop for
  Mac](https://docs.docker.com/desktop/setup/install/mac-install/).
- **Linux:** install [Docker Engine](https://docs.docker.com/engine/install/)
  and the [Docker Compose
  plugin](https://docs.docker.com/compose/install/linux/).

Start Docker Desktop or the Docker service, then verify all three commands:

```bash
docker --version
docker compose version
docker info
```

If `docker info` fails, Docker is installed but its service is not running yet.
Resolve that before continuing.

### 3. Understand the database and model prerequisites

The default manual commands below run **PostgreSQL with pgvector** and
**Ollama** in Docker containers. Docker downloads those images automatically;
you do not need to install PostgreSQL or Ollama separately on the computer.
Allow at least 20 GiB of free disk space and keep an internet connection active
for the first image and model downloads.

Native Ollama is optional and is mainly useful for direct GPU/Metal access.
If you choose that arrangement, install it from the [official Ollama download
page](https://ollama.com/download), start it, verify `ollama --version`, and use
the native instructions in [GPU acceleration](#gpu-acceleration).

### 4. Configure the framework

From the cloned `LLM-Framework` folder, create the local configuration file
with the command for your platform:

macOS or Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor. Fill in the blank `POSTGRES_PASSWORD` and
`APP_ACCESS_TOKEN` values with two different random values of at least 32
letters and numbers each. A password manager can generate them. Do not commit
or share this file.

### 5. Start PostgreSQL and Ollama

```bash
docker compose up -d postgres ollama
docker compose exec ollama ollama pull qwen2.5-coder:7b     # or any model you prefer
docker compose exec ollama ollama pull nomic-embed-text     # required for document and repository search
docker compose ps
```

The `postgres` service should report healthy and the `ollama` service should be
running. If either service stops, inspect it with
`docker compose logs --tail=100 postgres ollama`.

### 6. Start the framework

```bash
docker compose up -d --build backend frontend
```

Open `http://localhost:3000` and paste your `APP_ACCESS_TOKEN` at the
login prompt. Before selecting a domain, open **Framework model** in the left rail and select the installed
model you want to use. The framework saves it as the active model profile.

Use the sun/moon switch in the top bar to change between the high-contrast
light and dark themes. The choice is saved only in that browser on the current
device. On a first visit, the interface follows the device's preferred color
scheme.

### Tune a domain without running benchmarks

Select a domain or sub-domain, open **Settings**, and expand **Domain model
settings**. The same controls are the first section in **Model Performance
Optimizer** under **Quick model tuning**. Each scope remembers its own model,
request context, maximum answer length, temperature, and
Precise/Balanced/Creative response style. Visible one-tap token choices avoid
digging through dropdown menus. A single suggested-
settings button uses Ollama's detected loaded allocation when available and a
conservative current value otherwise. Benchmarks are optional.

The left rail's **request** value is the context actually sent for that domain.
The performance panel's **Ollama loaded allocation** is a separate runtime
measurement and can legitimately be larger. The framework reserves answer
space and drops the oldest conversation turns first when a prompt grows, and a
response that reaches its answer limit is visibly marked instead of silently
stopping. See [Domain model settings](./docs/domain-model-settings.md).

### Make learning cards from an answer

After the assistant finishes a response, select **Make learning cards** directly
beneath that latest response. The active local model turns it into one short
summary and exactly four simple cards. The original response remains unchanged,
and saved cards return when the conversation is reopened. See
[`docs/learning-cards.md`](./docs/learning-cards.md).

### Organize documents locally

In a domain or sub-domain, open **Documents** and expand **AI document
organizer**. The framework can use a selected local Ollama model to propose
virtual folders and tags from filenames and short indexed excerpts. Review and
edit every suggestion, acknowledge the review, and then apply it. Original
files are never moved or renamed. See
[`docs/document-organizer.md`](./docs/document-organizer.md).

Text-based PDFs are extracted once during indexing, just like Markdown files;
chat retrieval uses the resulting chunks rather than rereading the source PDF.
Every uploaded document has a **View** control. Choose **Convert** beside a PDF
to keep a Markdown copy inside the same domain or sub-domain and virtual folder;
the copy can then be viewed or downloaded. It is linked to the source instead of
being indexed a second time. See
[`docs/pdf-to-markdown.md`](./docs/pdf-to-markdown.md).

### Local code repository search

Open a domain or sub-domain, choose the Documents tab, and select **Import
repository snapshot (.zip)**. Confirm the exact scope, archive name, and
compressed size. The framework validates and indexes a read-only snapshot
locally, then can retrieve cited excerpts by repository, relative path, and
line range when you chat in that exact scope.

Repository access is never inherited by a parent, child, or sibling. The
model receives no shell, Git, repository editing, dependency installation,
network, or arbitrary filesystem capability. Credential-like and generated
files are excluded before embedding; review the reported exclusions and the
original archive because automated secret detection cannot guarantee that a
repository contains no sensitive data. See
[`docs/code-repository-search.md`](./docs/code-repository-search.md).

### GPU acceleration

The `ollama` service runs CPU-only by default, which works everywhere
but is slow. To use an NVIDIA GPU:

- **Linux**: install the [NVIDIA Container
  Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
  then run `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`.
- **Windows**: same idea via Docker Desktop's WSL2 backend + the
  NVIDIA driver's WSL2 support.
- **Mac**: Docker cannot pass GPU/Metal access through to containers
  at all. Install [Ollama natively](https://ollama.com/download/mac)
  instead, then in `.env` set
  `OLLAMA_HOST=http://host.docker.internal:11434` and don't start the
  `ollama` service (`docker compose up -d postgres backend frontend`).

See the
[setup and deployment record](./docs/implemented-features.md#setup-and-deployment)
for the currently implemented deployment paths and boundaries.

## Manual / native setup (for development)

If you'd rather run things directly instead of in Docker:

- **Backend**: Python 3.13, FastAPI + SQLAlchemy + PostgreSQL 17 with
  the `pgvector` extension. See `backend/requirements.txt`;
  `python -m app.seed` bootstraps the database (idempotent, safe to
  rerun). Needs its own `backend/.env` — see `app/config.py` for the
  full list of settings.
- **Frontend**: Next.js 16 + TypeScript, no server-rendered data
  fetching (works standalone or wrapped as a desktop app later). Needs
  `frontend/.env.local` with `NEXT_PUBLIC_API_URL`.
- **Ollama**: any recent version, running locally or reachable over
  the network.

## Model performance optimizer

The local **Model Performance Optimizer** is available from the performance-gauge
tab in the right rail. Select an installed model to inspect the configured
Ollama connection, container/native/remote relationship, model metadata,
loaded context, runtime hardware, sensors, and evidence gaps. The processor-use
graphic makes CPU-only, GPU/accelerator-only, split, and not-yet-observed model
placement explicit. An unreachable Ollama endpoint produces an actionable
diagnostic report.

Reports and benchmarks in this panel are optional advanced measurement. Its
first section, **Quick model tuning**, lets ordinary users change per-domain
model, context, answer length, response style, and temperature without running
a benchmark. **Ollama loaded allocation** describes the
currently loaded runtime; it is not automatically the selected domain's
request context.

It provides a persistent baseline benchmark and a bounded **context
comparison**. Choose a goal and Quick or Standard mode, review up to four
context candidates clamped to the model's native limit and the framework safety
ceiling, and then start it. The background run survives page navigation,
exposes reconnectable progress, can be cancelled safely, and keeps complete or
partial results in local PostgreSQL.
It uses only built-in synthetic prompts and discards generated answers; private
conversations, documents, memories, and repositories are not benchmark input.
The run may temporarily use substantial CPU/GPU/memory and pauses known chat or
indexing work, but it does not unload unrelated models, restart Ollama, change
saved settings, overclock hardware, expose shell access to a model, or send
hardware/results to a cloud service.

The completed comparison reports separate latency, generation, memory, context,
power, reliability, and CPU/GPU-placement evidence. It shows Pareto tradeoffs,
visible versioned objective weights, confidence and its reasons, deltas from the
current context, failed/skipped candidates, and a plain-language recommendation.
Larger context does not win merely for being larger when the workload does not
need it. The user can explicitly keep the current settings or download a
redacted Markdown report. Confidence scoring v2 repeats each of the three
synthetic workloads twice in Quick mode or three times in Standard mode and
calculates variance only within matching workloads.

The **Review setting change** step shows the exact current → selected profile
context alongside the
optimizer recommendation, explains that
the framework sends this value to Ollama as `num_ctx` on each model request,
and rechecks the profile, model build, Ollama endpoint/version, hardware
evidence, native model limit, and safety ceiling. It applies only after warning
acknowledgement and exact confirmation. Apply is owner-authenticated,
compare-and-set protected, transactionally verified, and recorded in an
append-only local audit. One-click rollback is offered only while the profile
still has the applied value, so it cannot overwrite a newer change. No Ollama
restart is required. The ordinary model-switch endpoint cannot change context
and therefore cannot bypass this workflow. The main-model card distinguishes
the effective active profile context from the native maximum shown in the picker.
The recommendation is a default rather than a restriction: the user can enter
the winning value, another completed measured candidate, or a custom token
count. The preview labels that choice explicitly. An unmeasured custom value
adds a required performance/placement warning and remains bounded by the
framework ceiling and current model-native limit.
Historical reports are flagged when the currently inspected model, Ollama
version, runtime, or visible accelerators no longer match their captured evidence.

The implemented optimizer behavior and its present verification boundary are
summarized in the
[implemented-features record](./docs/implemented-features.md#model-performance-optimizer).

## Prompt Inspector controls

The right rail's **What the model sees** tab previews the same prompt assembly
used for real generation. Expand an implemented background layer to enable or
disable it for the selected domain or sub-domain. Choices are stored locally
per scope and affect the next preview and message; turning off conversation
history does not delete the saved conversation.

Framework security rules and model operating instructions are advanced model-
input controls and require explicit acknowledgement before they can be turned
off. These switches control what the model receives. They do not turn off
code-level authentication, ownership checks, retrieval isolation, archive
validation, or filesystem restrictions. Its implemented behavior is included
in the [implemented-features record](./docs/implemented-features.md#prompt-inspector).

Tests: `cd backend && .venv/bin/pytest` — a real-dependency isolation
test suite using PostgreSQL and Ollama rather than mocked substitutes. The
verified security properties are summarized in the
[implemented-features record](./docs/implemented-features.md#security-properties-verified-in-the-repository).

## Project structure

```text
backend/    FastAPI application (domains, document/code retrieval, memory, chat)
frontend/   Next.js application
docs/       Public implementation, verification, and security documentation
benchmark/  Standalone model comparison harness
scripts/    Native-install helper scripts (e.g. Ollama systemd tuning)
```

## Documentation

- [System guide](./docs/system-guide.md) — complete user-facing description of
  the framework, its workflows, architecture, data boundaries, and current
  limitations.
- [Implemented features](./docs/implemented-features.md) — concise inventory of
  functionality present in the repository.
- [Documentation index](./docs/README.md) — focused guides for setup, model
  settings, documents, repositories, learning cards, and deletion behavior.

## License

The software in this repository is [MIT licensed](./LICENSE).
