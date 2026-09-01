from __future__ import annotations

from pathlib import Path
import sys


def _import_root() -> Path:
    return Path(__file__).resolve().parent


if str(_import_root()) not in sys.path:
    sys.path.insert(0, str(_import_root()))

from llmf_setup.app import run_app  # noqa: E402


if __name__ == "__main__":
    run_app()
