from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from llmf_setup.integrity import require_production_integrity, verify_production_inputs


class IntegrityTests(unittest.TestCase):
    def test_source_mode_is_explicitly_development(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("llmf_setup.integrity._manifest_path", return_value=None):
            result = verify_production_inputs(Path(directory))
        self.assertEqual(result.status, "development")

    def test_packaged_manifest_verifies_matching_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "docker-compose.yml"
            target.write_text("services: {}\n")
            manifest = root / "integrity.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "algorithm": "sha256",
                        "files": {"docker-compose.yml": sha256(target.read_bytes()).hexdigest()},
                    }
                )
            )
            with patch("llmf_setup.integrity._manifest_path", return_value=manifest):
                result = verify_production_inputs(root)
                require_production_integrity(root)
            self.assertEqual(result.status, "verified")

    def test_packaged_manifest_rejects_modified_or_missing_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "docker-compose.yml"
            target.write_text("modified")
            manifest = root / "integrity.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "algorithm": "sha256",
                        "files": {
                            "docker-compose.yml": sha256(b"expected").hexdigest(),
                            "backend/Dockerfile": sha256(b"missing").hexdigest(),
                        },
                    }
                )
            )
            with patch("llmf_setup.integrity._manifest_path", return_value=manifest):
                result = verify_production_inputs(root)
                with self.assertRaises(ValueError):
                    require_production_integrity(root)
            self.assertEqual(result.status, "failed")
            self.assertEqual(set(result.mismatches), {"docker-compose.yml", "backend/Dockerfile"})


if __name__ == "__main__":
    unittest.main()
