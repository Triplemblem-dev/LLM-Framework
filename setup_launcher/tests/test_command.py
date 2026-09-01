from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from llmf_setup.command import display_command, run_command


class CommandTests(unittest.TestCase):
    def test_argument_array_is_not_interpreted_by_a_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "should-not-exist"
            payload = f"literal;touch {marker}"
            result = run_command((sys.executable, "-c", "import sys; print(sys.argv[1])", payload))
            self.assertTrue(result.ok)
            self.assertIn(payload, result.output)
            self.assertFalse(marker.exists())

    def test_timeout_is_bounded(self) -> None:
        result = run_command((sys.executable, "-c", "import time; time.sleep(5)"), timeout=1)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)

    def test_display_command_quotes_only_for_review(self) -> None:
        rendered = display_command(("tool", "two words", "--flag"))
        self.assertEqual(rendered, "tool 'two words' --flag")


if __name__ == "__main__":
    unittest.main()
