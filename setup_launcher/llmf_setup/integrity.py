from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys


@dataclass(frozen=True)
class IntegrityResult:
    status: str
    detail: str
    mismatches: tuple[str, ...] = ()


def _manifest_path() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return base / "setup_launcher" / "generated" / "integrity.json"


def verify_production_inputs(project_root: Path) -> IntegrityResult:
    manifest_path = _manifest_path()
    if manifest_path is None:
        return IntegrityResult(
            "development",
            "Running from source; packaged production-file integrity is not available.",
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or payload.get("algorithm") != "sha256":
            raise ValueError("unsupported integrity manifest")
        files = payload.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("empty integrity manifest")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return IntegrityResult("failed", f"Packaged integrity manifest is unavailable or invalid: {exc}")

    mismatches: list[str] = []
    root = project_root.resolve()
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            mismatches.append("invalid manifest entry")
            continue
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            mismatches.append(relative)
            continue
        if not target.is_file() or sha256(target.read_bytes()).hexdigest() != expected:
            mismatches.append(relative)
    if mismatches:
        shown = ", ".join(mismatches[:4])
        more = f" and {len(mismatches) - 4} more" if len(mismatches) > 4 else ""
        return IntegrityResult("failed", f"Production files do not match this launcher: {shown}{more}.", tuple(mismatches))
    return IntegrityResult("verified", f"Verified {len(files)} production build inputs against the packaged launcher.")


def require_production_integrity(project_root: Path) -> None:
    result = verify_production_inputs(project_root)
    if result.status == "failed":
        raise ValueError(result.detail)
