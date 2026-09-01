# Local Setup Launcher

The repository includes unit-tested launcher source and GitHub Actions
packaging. Public artifacts are currently unsigned, and clean-machine
operating-system acceptance is outside automated CI.

## Outcome

The production repository now contains a standalone Tk desktop launcher in
`setup_launcher/`. It configures and starts a single-machine installation
before the normal backend exists. It is not a backend endpoint, model tool,
domain tool, or permanent privileged service.

The launcher provides three tabs:

1. **System check** — operating system, Docker, Compose, Docker service,
   Ollama, accelerator detection, disk, ports, and existing `.env`.
2. **Configure and install** — repository folder, native/bundled/remote Ollama,
   model tags, redacted existing-configuration preview, and explicit replacement
   consent.
3. **Progress** — named stages, actionable failures, verified completion,
   framework opening, and deliberate recovery-token copying.

Docker images contain PostgreSQL, pgvector, Python, Node.js, and application
dependencies. Users do not install those packages individually.

## Supported prerequisite paths

| Platform | Docker | Ollama |
| --- | --- | --- |
| Windows | Confirmed fixed `winget` package `Docker.DockerDesktop`, with official guide fallback | Confirmed fixed `winget` package `Ollama.Ollama`, with official guide fallback |
| macOS | Confirmed Homebrew cask `docker`, with official guide fallback | Confirmed Homebrew cask `ollama-app`, with official guide fallback |
| Linux | Official distribution-specific Docker instructions | Official Ollama download instructions |

Linux installation remains guided because running a remote convenience script
as root would violate the launcher boundary, and repository/package/init-system
choices differ by distribution.

## Ollama modes

- **Native** uses `http://host.docker.internal:11434`. The Compose backend has
  an explicit `host-gateway` mapping for Linux; Docker Desktop supplies the name
  on macOS and Windows.
- **Bundled** uses `http://ollama:11434` and explicitly starts the Compose
  Ollama service. The backend no longer has a hard dependency that would
  accidentally start bundled Ollama in native/remote mode.
- **Remote** accepts a validated HTTP(S) URL without embedded credentials,
  queries `/api/version`, and clearly means prompts leave the local computer.

Native and bundled setup pull the selected chat and embedding models. Remote
setup does not mutate the remote machine. After containers start, success
requires all three checks:

1. backend `/health` is reachable and valid JSON;
2. frontend is reachable; and
3. the backend container itself can reach the configured Ollama `/api/version`.

The launcher then selects the requested chat model through the authenticated
production model-profile API. Model activation failure is a setup failure, not
a successful installation.

## Configuration safety

The launcher generates the PostgreSQL password and access token with Python's
`secrets` module, backed by the operating-system CSPRNG. It writes `.env` through
an owner-restricted temporary file, flushes it, and atomically replaces the
destination.

Existing configuration is preserved by default and controls the retry's Ollama
mode. Replacement requires a separate checkbox and confirmation, first creates
a timestamped atomic backup, and never exposes secret values in the preview.
`.env`, backup, and temporary patterns are ignored by Git.

Secrets are not command arguments, URLs, logs, analytics, or crash reports. The
PostgreSQL password is never shown. The recovery access token is copied only
after explicit user action.

## Command boundary

All commands are fixed argument arrays executed with `shell=False`, bounded
timeouts, disabled stdin, and bounded captured output. The GUI shows the exact
allow-listed `winget` or Homebrew command before requesting installation
consent. Model tags are validated before they become `ollama pull` arguments.

The launcher never mounts the Docker socket into an application container and
does not create a host-command API. Its process exits when the window closes.

## Accelerator language

Preflight distinguishes three evidence levels:

- **detected:** supported NVIDIA tooling or Apple silicon is visible;
- **available:** the launcher may recommend a compatible Ollama mode but does
  not promise successful accelerator use; and
- **observed:** only the existing Model Performance Optimizer, after a model is
  loaded, reports actual CPU/accelerator placement.

The base bundled Compose configuration remains CPU-capable and does not promise
GPU acceleration.

## Packaging

`.github/workflows/setup-launcher.yml` tests the launcher on Windows, macOS, and
Linux, builds platform-specific PyInstaller artifacts, and creates platform
bundles from `git archive HEAD`. Consequently, local `.env`, Docker data,
caches, untracked files, or local workspaces cannot enter an artifact.

The macOS specification targets a universal2 application so one artifact
supports both Intel and Apple-silicon Macs when the runner's Python/Tk inputs
contain both architectures. The build fails instead of silently thinning an
incompatible dependency.

Before packaging, the workflow generates a SHA-256 manifest covering Compose
and every backend/frontend image build input. The manifest is embedded inside
the launcher. A packaged launcher refuses to execute Compose when adjacent
production inputs are missing or modified, preventing the folder picker from
becoming a path to execute an unrelated Compose project. Source mode labels
itself as unverified development mode.

CI artifacts are unsigned. A public release must add maintainer-owned Windows
Authenticode signing plus macOS signing/notarization. Those private credentials
must live in protected repository/environment secrets, never source control.

## Verification

The default launcher tests use temporary directories and mocks. They cover:

- shell-metacharacter isolation and command timeouts;
- malformed endpoints, credentials in URLs, and invalid model tags;
- CSPRNG configuration without placeholder secrets;
- owner-only writes and temporary-file cleanup;
- preservation, redaction, atomic backup, simulated interrupted replacement,
  and restart-safe retry;
- unavailable Docker and unreachable Ollama before configuration mutation;
- saved-mode reuse;
- low disk and port-conflict reporting;
- Windows/macOS allow-listed installers and Linux official-guide behavior; and
- backend-to-Ollama health failure not being reported as success.

Real package installation, Docker startup, image/model downloads, signing, and
OS-native application behavior are deliberately excluded from default CI and
must be supervised on clean disposable machines.

## Implemented safeguards

- Configuration is completed before backend startup, and the normal launcher
  flow does not require manual `.env` editing.
- Secrets use the operating-system CSPRNG and are excluded from command
  arguments, URLs, logs, and uploads.
- Native, bundled, and remote Ollama modes are explicit. Remote URLs are
  validated and tested both from the host and from the backend container.
- The launcher is a native Tk application, not a local web server.
- Commands use fixed argument arrays without a shell, with bounded time and
  output and redacted user-facing failures.
- Application services receive no Docker-socket access.
- Existing configuration is preserved by default. Replacement requires a
  preview and confirmation and creates a recoverable backup.
- POSIX writes use owner-only permissions. Every platform uses atomic
  same-volume replacement, while Windows uses the most restrictive available
  standard-library file mode. A signed Windows acceptance pass must verify the
  resulting ACLs.
- Progress uses named stages and next actions. Completion requires backend,
  frontend, and backend-to-Ollama checks.
- No setup service survives the launcher process.
- Accelerator reporting distinguishes detected, available, and observed
  evidence.
- Mocked tests cover the documented failure classes. Real operating-system
  acceptance remains supervised and outside default automation.

## Current distribution boundary

The source launcher and packaging workflow are complete, but generated public
artifacts are not yet signed or notarized. Clean-machine acceptance and Windows
ACL inspection are manual release checks, not claims made by this repository.
The setup launcher also intentionally does not provide uninstall or
backup/import behavior and never removes volumes, models, documents, or
databases.
