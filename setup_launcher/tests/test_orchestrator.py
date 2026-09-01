from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from llmf_setup.command import CommandResult
from llmf_setup.config import SetupOptions
from llmf_setup.orchestrator import SetupFailure, perform_setup


def project(directory: str) -> Path:
    root = Path(directory)
    (root / "docker-compose.yml").touch()
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    return root


def options(root: Path, mode: str = "native", endpoint: str = "http://host.docker.internal:11434") -> SetupOptions:
    return SetupOptions(root, mode, endpoint, "chat:latest", "embed:latest")


def ok(args=("test",), output="ok") -> CommandResult:
    return CommandResult(tuple(args), 0, output)


class OrchestratorTests(unittest.TestCase):
    def test_invalid_project_folder_has_actionable_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(SetupFailure) as raised:
                perform_setup(options(root), lambda *_args: None)
            self.assertEqual(raised.exception.stage, "validation")
            self.assertIn("Correct", raised.exception.action)

    @patch("llmf_setup.orchestrator._wait_for_http", return_value=True)
    @patch("llmf_setup.orchestrator._activate_model", return_value=True)
    @patch("llmf_setup.orchestrator._verify_ollama_from_backend", return_value=ok())
    @patch("llmf_setup.orchestrator._compose", return_value=ok())
    @patch("llmf_setup.orchestrator._pull_native", return_value=ok())
    @patch("llmf_setup.orchestrator.test_ollama_endpoint", return_value=True)
    @patch("llmf_setup.orchestrator.run_command", return_value=ok())
    @patch("llmf_setup.orchestrator.find_executable", return_value="/usr/local/bin/tool")
    def test_native_setup_writes_config_pulls_models_and_checks_both_services(
        self, _which, _run, _endpoint, pull, compose, verify_backend, activate, wait_http
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            events = []
            result = perform_setup(options(root), lambda stage, detail: events.append((stage, detail)))
            self.assertTrue(result.configuration.created)
            self.assertEqual(pull.call_count, 2)
            verify_backend.assert_called_once_with(root.resolve())
            activate.assert_called_once_with("chat:latest", result.configuration.access_token)
            self.assertEqual(wait_http.call_count, 2)
            self.assertEqual(events[-1][0], "complete")
            compose.assert_any_call(root.resolve(), ("up", "-d", "postgres"))

    @patch("llmf_setup.orchestrator.find_executable", return_value=None)
    def test_missing_docker_stops_before_configuration(self, _which) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            with self.assertRaises(SetupFailure) as raised:
                perform_setup(options(root), lambda *_args: None)
            self.assertEqual(raised.exception.stage, "preflight")
            self.assertFalse((root / ".env").exists())

    @patch("llmf_setup.orchestrator.test_ollama_endpoint", return_value=False)
    @patch("llmf_setup.orchestrator.run_command", return_value=ok())
    @patch("llmf_setup.orchestrator.find_executable", return_value="/usr/bin/docker")
    def test_unreachable_remote_stops_before_configuration(self, _which, _run, _endpoint) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            remote = options(root, "remote", "https://models.example.test")
            with self.assertRaises(SetupFailure) as raised:
                perform_setup(remote, lambda *_args: None)
            self.assertEqual(raised.exception.stage, "preflight")
            self.assertFalse((root / ".env").exists())

    @patch("llmf_setup.orchestrator._wait_for_http", return_value=True)
    @patch("llmf_setup.orchestrator._activate_model", return_value=True)
    @patch("llmf_setup.orchestrator._verify_ollama_from_backend", return_value=ok())
    @patch("llmf_setup.orchestrator._pull_bundled", return_value=ok())
    @patch("llmf_setup.orchestrator._compose", return_value=ok())
    @patch("llmf_setup.orchestrator.run_command", return_value=ok())
    @patch("llmf_setup.orchestrator.find_executable", return_value="/usr/bin/docker")
    def test_existing_configuration_controls_mode(
        self, _which, _run, compose, pull_bundled, _verify, _activate, _wait
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            original = "APP_ACCESS_TOKEN=keep\nOLLAMA_HOST=http://ollama:11434\n"
            (root / ".env").write_text(original)
            result = perform_setup(options(root), lambda *_args: None)
            self.assertFalse(result.configuration.created)
            self.assertEqual((root / ".env").read_text(), original)
            self.assertEqual(pull_bundled.call_count, 2)
            compose.assert_any_call(root.resolve(), ("up", "-d", "postgres", "ollama"))

    @patch("llmf_setup.orchestrator._wait_for_http", return_value=True)
    @patch("llmf_setup.orchestrator._activate_model", return_value=True)
    @patch("llmf_setup.orchestrator._verify_ollama_from_backend", return_value=CommandResult(("verify",), 1, "failed"))
    @patch("llmf_setup.orchestrator._compose", return_value=ok())
    @patch("llmf_setup.orchestrator._pull_native", return_value=ok())
    @patch("llmf_setup.orchestrator.test_ollama_endpoint", return_value=True)
    @patch("llmf_setup.orchestrator.run_command", return_value=ok())
    @patch("llmf_setup.orchestrator.find_executable", return_value="/usr/bin/tool")
    def test_backend_to_ollama_failure_is_not_reported_as_success(self, *_mocks) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            with self.assertRaises(SetupFailure) as raised:
                perform_setup(options(root), lambda *_args: None)
            self.assertEqual(raised.exception.stage, "health")

    @patch("llmf_setup.orchestrator._wait_for_http", return_value=True)
    @patch("llmf_setup.orchestrator._activate_model", return_value=False)
    @patch("llmf_setup.orchestrator._verify_ollama_from_backend", return_value=ok())
    @patch("llmf_setup.orchestrator._compose", return_value=ok())
    @patch("llmf_setup.orchestrator._pull_native", return_value=ok())
    @patch("llmf_setup.orchestrator.test_ollama_endpoint", return_value=True)
    @patch("llmf_setup.orchestrator.run_command", return_value=ok())
    @patch("llmf_setup.orchestrator.find_executable", return_value="/usr/bin/tool")
    def test_model_activation_failure_is_not_reported_as_success(self, *_mocks) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            with self.assertRaises(SetupFailure) as raised:
                perform_setup(options(root), lambda *_args: None)
            self.assertEqual(raised.exception.stage, "model-profile")


if __name__ == "__main__":
    unittest.main()
