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

## Quick start

The main installation method is GitHub cloning plus Docker Compose. Docker runs
PostgreSQL, Ollama, the backend, and the frontend for you; you do not need to
install PostgreSQL, Python, Node.js, or Ollama separately for this default path.

### 1. Install Git and Docker

Install [Git](https://git-scm.com/downloads/) and Docker for your operating
system:

- [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Docker Desktop for macOS](https://docs.docker.com/desktop/setup/install/mac-install/)
- [Docker Engine for Linux](https://docs.docker.com/engine/install/) plus the
  [Docker Compose plugin](https://docs.docker.com/compose/install/linux/)

Start Docker Desktop or the Docker service, then check that everything is
ready:

```bash
git --version
docker --version
docker compose version
docker info
```

If `docker info` fails, Docker is installed but not running yet.

### 2. Clone the project and enter its folder

Open a terminal in the parent folder where you want to keep the project. For
example, if you created a folder named `Testing`:

```bash
git clone https://github.com/Triplemblem-dev/LLM-Framework.git
cd LLM-Framework
```

On Windows PowerShell, the same clone commands work; use the appropriate path
for your parent folder, for example `cd $HOME\Testing`.

Now verify that the terminal is inside the repository:

macOS or Linux:

```bash
pwd
ls -la .env.example docker-compose.yml
```

Windows PowerShell:

```powershell
Get-Location
Get-ChildItem -Force .env.example,docker-compose.yml
```

Both `.env.example` and `docker-compose.yml` must be listed before continuing.

### 3. Create the private `.env` file

Run exactly one command from inside the cloned `LLM-Framework` folder.

macOS or Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

The new file is located here:

```text
<the cloned LLM-Framework folder>/.env
```

Examples:

- macOS: `/Users/your-name/Testing/LLM-Framework/.env`
- Linux: `/home/your-name/Testing/LLM-Framework/.env`
- Windows: `C:\Users\your-name\Testing\LLM-Framework\.env`

Files beginning with a dot are hidden by default on macOS and Linux. You can
still open `.env` from a text editor. On macOS Finder, press
<kbd>Command</kbd>+<kbd>Shift</kbd>+<kbd>.</kbd> to show hidden files.

### 4. Set your two private values

Open `.env` and find these lines:

```dotenv
POSTGRES_PASSWORD=
APP_ACCESS_TOKEN=
```

Give each one a different random value of at least 32 letters and numbers. A
password manager is the easiest safe generator. On macOS or Linux,
`openssl rand -hex 32` creates a portable 64-character value. Do not add quotes
or spaces around the values. Save the file.

- `POSTGRES_PASSWORD` protects the framework database.
- `APP_ACCESS_TOKEN` is the password you paste into the framework login screen.
- `.env` is ignored by Git and must never be committed, posted, or shared.

Choosing your own strong `APP_ACCESS_TOKEN` during installation is encouraged.
You can change it later too: edit only `APP_ACCESS_TOKEN` in `.env`, save it,
then run:

```bash
docker compose up -d --build backend frontend
```

Reload the browser and sign in with the new token. Do not change
`POSTGRES_PASSWORD` after the database has been initialized unless you also
rotate the password inside PostgreSQL; changing only the `.env` line would
disconnect the backend from the existing database. Follow the
[database-password guide](./docs/database-passwords.md) to preserve the data or
perform an explicitly destructive fresh reset.

### 5. Start the database and local model service

Allow at least 20 GiB of free disk space and keep an internet connection active
for the first image and model downloads.

```bash
docker compose up -d postgres ollama
```

Download one chat model:

```bash
docker compose exec ollama ollama pull qwen2.5-coder:7b
```

Download the embedding model required for document and repository search:

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

### 6. Build and open the framework

```bash
docker compose up -d --build backend frontend
docker compose ps
```

In `docker compose ps`, `postgres`, `ollama`, `backend`, and `frontend` should
be running. Open [http://localhost:3000](http://localhost:3000) and paste the
`APP_ACCESS_TOKEN` from your `.env` file.

Before selecting a domain, open **Framework model** in the left rail and select
the model you downloaded. The framework remembers it as the active model.

If a service is not running, inspect the latest logs:

```bash
docker compose logs --tail=100 postgres ollama backend frontend
```

If the backend reports `password authentication failed`, do not keep recreating
only the backend. Follow the [database-password guide](./docs/database-passwords.md)
to repair the PostgreSQL credential mismatch.

GitHub also has a [cloning guide](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository)
if you need more help with Git on Windows, macOS, or Linux.

### Update the framework

From the folder that contains your cloned repository, run:

```bash
cd LLM-Framework
git pull --ff-only
docker compose up -d --build
```

This keeps your `.env`, database, documents, and downloaded Docker Ollama
models. Do not add `-v` to an update command because it deletes the stored
Docker volumes.

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

Open **Model Performance Optimizer** from the performance-gauge tab in the
right rail. Its first section, **Quick model tuning**, makes it easy to
fine-tune how the model responds in each domain or sub-domain. Change the model,
request context, maximum answer length, response style, and temperature with
simple controls; each scope remembers its own settings, and no benchmark is
required.

The advanced section can inspect the Ollama connection, model metadata,
hardware, loaded context, and CPU/GPU placement. Optional context comparisons
use only built-in synthetic prompts and keep private conversations, documents,
memories, and repositories out of benchmark input. Recommendations are never
applied automatically: users review and confirm a setting change, and safe
rollback is available when no newer setting would be overwritten.

The interface also distinguishes a domain's request context from Ollama's
loaded allocation and the model's native limit, so users can tune performance
without confusing those values.

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
