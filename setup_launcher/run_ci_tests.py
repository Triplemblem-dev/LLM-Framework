from __future__ import annotations

import io
from pathlib import Path
import sys
import unittest


def _annotation_value(value: str) -> str:
    """Escape text for a GitHub Actions workflow-command annotation."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    tests = Path(__file__).resolve().parent / "tests"
    suite = unittest.defaultTestLoader.discover(str(tests))
    captured = io.StringIO()
    result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
    report = captured.getvalue()
    print(report, end="")
    if result.wasSuccessful():
        return 0

    # GitHub's public check annotations remain readable even when raw job logs
    # require repository-owner authentication. Include only failure details so
    # the annotation limit cannot truncate the useful traceback.
    failures = [
        f"{kind}: {test}\n{traceback}"
        for kind, entries in (("ERROR", result.errors), ("FAIL", result.failures))
        for test, traceback in entries
    ]
    diagnostic = _annotation_value("\n\n".join(failures)[-7_000:])
    print(f"::error title=Launcher unit tests failed::{diagnostic}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
