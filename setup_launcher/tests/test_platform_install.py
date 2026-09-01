from __future__ import annotations

import unittest
from unittest.mock import patch

from llmf_setup.platform_install import install_plan


class InstallPlanTests(unittest.TestCase):
    @patch("llmf_setup.platform_install.find_executable", return_value="C:/winget.exe")
    def test_windows_uses_fixed_winget_package_ids(self, _which) -> None:
        docker = install_plan("docker", "Windows")
        ollama = install_plan("ollama", "Windows")
        self.assertEqual(docker.command[0:4], ("winget", "install", "--id", "Docker.DockerDesktop"))  # type: ignore[index]
        self.assertEqual(ollama.command[0:4], ("winget", "install", "--id", "Ollama.Ollama"))  # type: ignore[index]
        self.assertIn("--exact", docker.command or ())

    @patch("llmf_setup.platform_install.find_executable", return_value="/opt/homebrew/bin/brew")
    def test_macos_uses_fixed_homebrew_casks(self, _which) -> None:
        self.assertEqual(install_plan("docker", "Darwin").command, ("brew", "install", "--cask", "docker"))
        self.assertEqual(install_plan("ollama", "Darwin").command, ("brew", "install", "--cask", "ollama-app"))

    @patch("llmf_setup.platform_install.find_executable", return_value=None)
    def test_linux_opens_official_guides_instead_of_root_script(self, _which) -> None:
        docker = install_plan("docker", "Linux")
        ollama = install_plan("ollama", "Linux")
        self.assertIsNone(docker.command)
        self.assertIsNone(ollama.command)
        self.assertTrue(docker.official_url.startswith("https://docs.docker.com/"))
        self.assertEqual(ollama.official_url, "https://ollama.com/download")

    def test_unknown_dependency_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            install_plan("arbitrary-tool")


if __name__ == "__main__":
    unittest.main()
