from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from llmf_setup.command import CommandResult
from llmf_setup.preflight import run_preflight


def successful_runner(args, **_kwargs):
    return CommandResult(tuple(args), 0, "test-version")


class PreflightTests(unittest.TestCase):
    @patch("llmf_setup.preflight.find_executable", return_value="/usr/bin/tool")
    @patch("llmf_setup.preflight.check_ollama")
    def test_preflight_is_read_only_and_reports_existing_configuration(self, ollama_check, _which) -> None:
        from llmf_setup.preflight import Check

        ollama_check.return_value = Check("ollama-service", "Ollama service", "ready", "Reachable", "None")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("APP_ACCESS_TOKEN=secret")
            checks = run_preflight(root, runner=successful_runner)
            keyed = {check.key: check for check in checks}
            self.assertEqual(keyed["docker-cli"].status, "ready")
            self.assertEqual(keyed["compose"].status, "ready")
            self.assertEqual(keyed["configuration"].status, "warning")
            self.assertEqual((root / ".env").read_text(), "APP_ACCESS_TOKEN=secret")

    @patch("llmf_setup.preflight.find_executable", return_value=None)
    @patch("llmf_setup.preflight.check_ollama")
    def test_port_conflict_and_low_disk_are_actionable(self, ollama_check, _which) -> None:
        from collections import namedtuple
        from llmf_setup.preflight import Check

        ollama_check.return_value = Check("ollama-service", "Ollama service", "missing", "No", "Install")
        usage = namedtuple("usage", "total used free")(100 * 1024**3, 96 * 1024**3, 4 * 1024**3)

        class FakeSocket:
            def setsockopt(self, *_args):
                return None

            def bind(self, address):
                if address[1] == 3000:
                    raise OSError("occupied")

            def close(self):
                return None

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("llmf_setup.preflight.shutil.disk_usage", return_value=usage),
            patch("llmf_setup.preflight.socket.socket", return_value=FakeSocket()),
        ):
            checks = run_preflight(Path(directory), runner=successful_runner)
        keyed = {check.key: check for check in checks}
        self.assertEqual(keyed["port-3000"].status, "warning")
        self.assertIn("Stop", keyed["port-3000"].action)
        self.assertEqual(keyed["disk"].status, "missing")
        self.assertIn("Free disk", keyed["disk"].action)


if __name__ == "__main__":
    unittest.main()
