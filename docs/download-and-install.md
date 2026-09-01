# Download and install

Packaged releases are intended for people who do not use Git or the command
line. A release ZIP contains the application source required by Docker and the
matching graphical setup launcher in one folder.

## Download from GitHub

1. Open the LLM Framework repository page in a web browser.
2. Find **Releases** on the right side of the page. On a narrow screen, open the
   repository's **Releases** section from the page navigation.
3. Select the release labelled **Latest**.
4. Under **Assets**, select exactly one download:

   | Computer | Download |
   | --- | --- |
   | Windows 10/11, 64-bit | `LLM-Framework-Windows-x64.zip` |
   | Intel or Apple-silicon Mac | `LLM-Framework-macOS-Universal.zip` |
   | 64-bit Linux | `LLM-Framework-Linux-x64.zip` |

5. Wait for the ZIP to finish downloading, then extract the entire archive.
   Do not run the launcher from inside the ZIP preview.

The green **Code → Download ZIP** button downloads source code, not the
packaged launcher. It is useful for developers but is not the recommended
installation route.

## Start the graphical setup

### Windows

Open the extracted folder and double-click `LLM-Framework-Setup.exe`.

### macOS

Open the extracted folder and double-click `LLM-Framework-Setup.app`.

### Linux

Open the extracted folder and launch `LLM-Framework-Setup`. Desktop
environments differ; some require opening file **Properties → Permissions**
and enabling **Allow executing file as program** first.

The launcher checks Docker, Docker Compose, Ollama, available ports, disk
space, and existing configuration. It offers supported installation actions or
opens the official platform instructions, then guides the user through model
selection and verifies the running framework.

## Current trust and compatibility boundary

The automated release workflow publishes a `SHA256SUMS.txt` file so downloads
can be verified. The current CI artifacts are not code-signed or notarized.
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
