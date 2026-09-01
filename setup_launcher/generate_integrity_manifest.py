from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "setup_launcher" / "generated" / "integrity.json"


def included_files() -> list[Path]:
    explicit = [
        ROOT / "docker-compose.yml",
        ROOT / "docker-compose.gpu.yml",
        ROOT / "backend" / ".dockerignore",
        ROOT / "backend" / "Dockerfile",
        ROOT / "backend" / "requirements.txt",
        ROOT / "frontend" / ".dockerignore",
        ROOT / "frontend" / "Dockerfile",
        ROOT / "frontend" / "package.json",
        ROOT / "frontend" / "package-lock.json",
        ROOT / "frontend" / "next.config.mjs",
        ROOT / "frontend" / "tsconfig.json",
    ]
    discovered: list[Path] = []
    for directory in (ROOT / "backend" / "app", ROOT / "frontend" / "app", ROOT / "frontend" / "components", ROOT / "frontend" / "lib"):
        discovered.extend(path for path in directory.rglob("*") if path.is_file())
    files = explicit + discovered
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise SystemExit("Missing production input: " + ", ".join(str(path.relative_to(ROOT)) for path in missing))
    return sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())


def main() -> None:
    entries = {
        path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in included_files()
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"schema_version": 1, "algorithm": "sha256", "files": entries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(entries)} production inputs")


if __name__ == "__main__":
    main()
