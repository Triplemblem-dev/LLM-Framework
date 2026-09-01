from __future__ import annotations

from dataclasses import dataclass
import platform

from .command import find_executable


DOCKER_URLS = {
    "Windows": "https://docs.docker.com/desktop/setup/install/windows-install/",
    "Darwin": "https://docs.docker.com/desktop/setup/install/mac-install/",
    "Linux": "https://docs.docker.com/engine/install/",
}
OLLAMA_URL = "https://ollama.com/download"


@dataclass(frozen=True)
class InstallPlan:
    dependency: str
    method: str
    command: tuple[str, ...] | None
    official_url: str
    explanation: str


def install_plan(dependency: str, system: str | None = None) -> InstallPlan:
    system = system or platform.system()
    if dependency not in {"docker", "ollama"}:
        raise ValueError("Unknown dependency")

    official_url = DOCKER_URLS.get(system, "https://docs.docker.com/get-docker/") if dependency == "docker" else OLLAMA_URL

    if system == "Windows" and find_executable("winget"):
        package = "Docker.DockerDesktop" if dependency == "docker" else "Ollama.Ollama"
        return InstallPlan(
            dependency,
            "winget",
            (
                "winget",
                "install",
                "--id",
                package,
                "--exact",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ),
            official_url,
            "Windows Package Manager will download the named package after confirmation.",
        )

    if system == "Darwin" and find_executable("brew"):
        package = "docker" if dependency == "docker" else "ollama-app"
        return InstallPlan(
            dependency,
            "homebrew",
            ("brew", "install", "--cask", package),
            official_url,
            "Homebrew will install the official desktop application after confirmation.",
        )

    detail = (
        "Linux installation differs by distribution and requires administrator choices. "
        "The launcher opens the official instructions instead of running a remote script as root."
        if system == "Linux"
        else "No supported local package manager was detected; use the official installer."
    )
    return InstallPlan(dependency, "official-guide", None, official_url, detail)
