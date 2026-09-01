from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from llmf_setup.config import (
    SetupOptions,
    existing_ollama_mode,
    read_access_token,
    redacted_env_preview,
    validate_endpoint,
    validate_model_tag,
    write_configuration,
)


def project(directory: str) -> Path:
    root = Path(directory)
    (root / "docker-compose.yml").touch()
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    return root


class ConfigTests(unittest.TestCase):
    def options(self, root: Path, *, replace: bool = False) -> SetupOptions:
        return SetupOptions(
            project_root=root,
            ollama_mode="native",
            ollama_endpoint="http://host.docker.internal:11434",
            chat_model="qwen2.5-coder:7b",
            embedding_model="nomic-embed-text",
            replace_existing=replace,
        )

    def test_new_configuration_is_atomic_owner_only_and_not_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            with patch("llmf_setup.config.secrets.token_hex", side_effect=("a" * 64, "b" * 64)):
                result = write_configuration(self.options(root))
            content = (root / ".env").read_text()
            self.assertTrue(result.created)
            self.assertEqual(result.access_token, "a" * 64)
            self.assertIn("POSTGRES_PASSWORD=" + "b" * 64, content)
            self.assertIn("APP_ACCESS_TOKEN=" + "a" * 64, content)
            self.assertNotIn("changeme", content)
            if os.name != "nt":
                self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(root.glob(".env.tmp-*")), [])

    def test_existing_configuration_is_preserved_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            original = "APP_ACCESS_TOKEN=keep-me\nOLLAMA_HOST=http://ollama:11434\n"
            (root / ".env").write_text(original)
            result = write_configuration(self.options(root))
            self.assertFalse(result.created)
            self.assertEqual((root / ".env").read_text(), original)
            self.assertEqual(result.access_token, "keep-me")

    def test_malformed_existing_configuration_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            original = "OLLAMA_HOST=http://ollama:11434\n"
            (root / ".env").write_text(original)
            with self.assertRaises(FileExistsError):
                write_configuration(self.options(root))
            self.assertEqual((root / ".env").read_text(), original)

    def test_replacement_creates_redactable_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            (root / ".env").write_text("APP_ACCESS_TOKEN=old-secret\nOLLAMA_HOST=http://ollama:11434\n")
            result = write_configuration(self.options(root, replace=True))
            self.assertIsNotNone(result.backup_path)
            self.assertIn("old-secret", result.backup_path.read_text())  # type: ignore[union-attr]
            self.assertNotIn("old-secret", (root / ".env").read_text())
            self.assertNotIn("old-secret", redacted_env_preview(result.backup_path))  # type: ignore[arg-type]

    def test_interrupted_replacement_preserves_original_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            original = "APP_ACCESS_TOKEN=old-secret\nOLLAMA_HOST=http://ollama:11434\n"
            (root / ".env").write_text(original)
            real_replace = os.replace

            def fail_only_final(source, destination):
                if Path(destination).name == ".env":
                    raise OSError("simulated interruption")
                return real_replace(source, destination)

            with patch("llmf_setup.config.os.replace", side_effect=fail_only_final):
                with self.assertRaises(OSError):
                    write_configuration(self.options(root, replace=True))
            self.assertEqual((root / ".env").read_text(), original)
            self.assertEqual(list(root.glob(".env.tmp-*")), [])
            self.assertEqual(len(list(root.glob(".env.backup-*"))), 1)

    def test_rerun_reuses_generated_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = project(directory)
            first = write_configuration(self.options(root))
            original = (root / ".env").read_text()
            second = write_configuration(self.options(root))
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(second.access_token, first.access_token)
            self.assertEqual((root / ".env").read_text(), original)

    def test_existing_mode_is_derived_from_saved_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OLLAMA_HOST=http://host.docker.internal:11434\nAPP_ACCESS_TOKEN=x\n")
            self.assertEqual(existing_ollama_mode(path), ("native", "http://host.docker.internal:11434"))
            self.assertEqual(read_access_token(path), "x")

    def test_endpoints_reject_credentials_and_non_http_schemes(self) -> None:
        for value in ("file:///tmp/ollama", "http://user:pass@example.com", "javascript:alert(1)"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_endpoint(value)

    def test_model_tags_reject_shell_metacharacters(self) -> None:
        self.assertEqual(validate_model_tag("org/model:tag", "Model"), "org/model:tag")
        for value in ("model;rm", "model $(id)", "--option", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_model_tag(value, "Model")


if __name__ == "__main__":
    unittest.main()
