# Download and install

## Current recommended method: clone from GitHub

The current supported path is:

```bash
git clone https://github.com/Triplemblem-dev/LLM-Framework.git
cd LLM-Framework
```

Then follow the six numbered steps in the main [Quick start](../README.md#quick-start).
Those steps install prerequisites, locate the private `.env`, start Docker
services, download models, and select the active framework model.

The most common setup mistake is running commands from the parent folder. If
the terminal prompt says `Testing %`, but the repository was cloned as
`Testing/LLM-Framework`, run:

```bash
cd LLM-Framework
```

You should be able to list both files below before copying the environment
template:

```bash
ls -la .env.example docker-compose.yml
```

## Download ZIP without learning Git

Someone who does not want to use Git can still download the source:

1. Open the repository on GitHub.
2. Select the green **Code** button.
3. Select **Download ZIP**.
4. Extract the entire ZIP to a permanent folder.
5. Open a terminal inside the extracted folder—the folder that directly
   contains `.env.example` and `docker-compose.yml`.
6. Continue at [Create the private `.env` file](../README.md#3-create-the-private-env-file).

The extracted directory may be named `LLM-Framework-main` rather than
`LLM-Framework`; the name does not matter. The two files above identify the
correct folder.

## Packaged graphical releases

The repository contains a graphical setup-launcher implementation and a
cross-platform release workflow, but a **Releases** page is useful only after
the maintainer has published a version tag and its builds have completed. If
GitHub shows no release assets, nothing is missing from your browser: use Git
clone or **Code → Download ZIP** instead.

Future packaged assets are designed to contain the application source required
by Docker plus the matching platform launcher in one extracted folder. They
must not be run from inside a ZIP preview.

## Current trust and compatibility boundary

The release workflow is designed to publish a `SHA256SUMS.txt` file so downloads
can be verified. Current launcher artifacts are not code-signed or notarized.
Windows SmartScreen or macOS Gatekeeper may therefore warn or block them even
when the download is intact. General non-technical distribution should begin
only after the maintainer adds Authenticode signing for Windows and Apple
Developer ID signing/notarization for macOS; users should not be trained to
ignore operating-system security warnings.

The Linux executable is built on Ubuntu 24.04 x64. Other distributions may
need a separately built package or may run the source launcher with Python 3
and Tk. Accelerator availability depends on the operating system, hardware,
drivers, and whether Ollama runs natively or in Docker; the launcher reports
evidence without promising GPU use.

## For the release maintainer

Pushing a version tag such as `v0.1.0` starts the cross-platform tests and
builds. After all three platform builds pass, GitHub Actions creates a Release,
attaches the three user ZIP files plus `SHA256SUMS.txt`, and generates release
notes.
