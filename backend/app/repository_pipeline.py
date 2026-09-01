"""Secure, local-only repository snapshot validation and indexing.

The pipeline accepts ZIP bytes supplied by the user, validates every member before reading
or writing it, extracts only conservative text/source files into an isolated staging root,
and generates embeddings through the already-configured local Ollama embedding model. It
never invokes Git, a shell, repository code, hooks, package managers, or network clients.
"""

from __future__ import annotations

import hashlib
import re
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.config import settings
from app.ollama_client import embed

MAX_ARCHIVE_BYTES = settings.repository_max_archive_bytes
MAX_UNCOMPRESSED_BYTES = settings.repository_max_uncompressed_bytes
MAX_MEMBERS = settings.repository_max_members
MAX_SEARCHABLE_FILE_BYTES = settings.repository_max_file_bytes
MAX_COMPRESSION_RATIO = settings.repository_max_compression_ratio
EMBED_BATCH_SIZE = 32
CHUNK_LINE_LIMIT = 60
CHUNK_CHAR_LIMIT = 4_000
CHUNK_LINE_OVERLAP = 8

LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".json": "json",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lua": "lua",
    ".md": "markdown",
    ".php": "php",
    ".proto": "protobuf",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scss": "scss",
    ".sh": "shell-text",
    ".sql": "sql",
    ".svelte": "svelte",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".txt": "text",
    ".vue": "vue",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}

EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "bower_components",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "site-packages",
    "target",
    "vendor",
    "venv",
}

SENSITIVE_DIRECTORIES = {".aws", ".azure", ".gnupg", ".ssh", "gcloud"}
SENSITIVE_SUFFIXES = {".der", ".jks", ".key", ".keystore", ".p12", ".pem", ".pfx"}
SENSITIVE_NAMES = {
    ".npmrc",
    ".pypirc",
    "auth.json",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
    "known_hosts",
    "netrc",
    "password-store.json",
    "secrets.json",
    "service-account.json",
    "token",
    "token.json",
    "tokens.json",
}

SECRET_PATTERNS = [
    ("private key material", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("probable AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("probable GitHub token", re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    (
        "probable assigned credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password)"
            r"\s*[:=]\s*[\"'][^\"'\r\n]{8,}[\"']"
        ),
    ),
]

SYMBOL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:class|def|enum|function|interface|module|namespace|record|struct|trait|type)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


class RepositoryValidationError(ValueError):
    pass


@dataclass
class PreparedChunk:
    chunk_index: int
    start_line: int
    end_line: int
    symbol: str | None
    content: str
    embedding: list[float] = field(default_factory=list)


@dataclass
class PreparedFile:
    relative_path: str
    language: str
    size_bytes: int
    content_hash: str
    chunks: list[PreparedChunk]


@dataclass
class PreparedSnapshot:
    content_hash: str
    files: list[PreparedFile]
    exclusions: list[dict]

    @property
    def skipped_file_count(self) -> int:
        return len(self.exclusions)

    @property
    def security_excluded_count(self) -> int:
        return sum(1 for item in self.exclusions if item["security"])

    @property
    def chunk_count(self) -> int:
        return sum(len(item.chunks) for item in self.files)


def _normalized_member_path(raw_name: str) -> PurePosixPath:
    if "\x00" in raw_name:
        raise RepositoryValidationError("Archive contains a path with a NUL byte")
    normalized = raw_name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise RepositoryValidationError("Archive contains an absolute or drive-qualified path")
    path = PurePosixPath(normalized)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RepositoryValidationError("Archive contains an unsafe relative path")
    return path


def _validate_member_type(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise RepositoryValidationError("Encrypted archive members are not supported")
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}:
        raise RepositoryValidationError("Archive contains a link or special filesystem entry")


def _path_exclusion(path: PurePosixPath) -> tuple[str, bool] | None:
    lowered_parts = [part.lower() for part in path.parts]
    if any(part in EXCLUDED_DIRECTORIES for part in lowered_parts[:-1]):
        return "dependency, cache, or generated directory", False
    if any(part in SENSITIVE_DIRECTORIES for part in lowered_parts[:-1]):
        return "sensitive credential directory", True
    basename = lowered_parts[-1]
    if basename == ".env" or basename.startswith(".env.") or basename in SENSITIVE_NAMES:
        return "sensitive credential filename", True
    if Path(basename).suffix.lower() in SENSITIVE_SUFFIXES:
        return "sensitive key or credential file", True
    if Path(basename).suffix.lower() not in LANGUAGES:
        return "unsupported or non-source file type", False
    return None


def _content_exclusion(data: bytes, text: str) -> tuple[str, bool] | None:
    if b"\x00" in data:
        return "binary content", False
    lines = text.splitlines()
    if lines and max(len(line) for line in lines) > 20_000:
        return "probable minified or generated content", False
    for reason, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return reason, True
    return None


def _chunk_source(text: str) -> list[PreparedChunk]:
    lines = text.splitlines()
    if not lines or not text.strip():
        return []
    chunks: list[PreparedChunk] = []
    start = 0
    index = 0
    while start < len(lines):
        end = start
        chars = 0
        while end < len(lines) and end - start < CHUNK_LINE_LIMIT:
            next_size = len(lines[end]) + 1
            if end > start and chars + next_size > CHUNK_CHAR_LIMIT:
                break
            chars += next_size
            end += 1
        if end == start:
            end += 1
        content = "\n".join(lines[start:end]).strip()
        if content:
            match = SYMBOL_RE.search(content)
            chunks.append(
                PreparedChunk(
                    chunk_index=index,
                    start_line=start + 1,
                    end_line=end,
                    symbol=match.group(1) if match else None,
                    content=content,
                )
            )
            index += 1
        if end >= len(lines):
            break
        start = max(start + 1, end - CHUNK_LINE_OVERLAP)
    return chunks


def prepare_repository_snapshot(archive_path: Path, staging_root: Path) -> PreparedSnapshot:
    try:
        archive_size = archive_path.stat().st_size
    except OSError as exc:
        raise RepositoryValidationError("Uploaded repository archive is unavailable") from exc
    if not archive_size:
        raise RepositoryValidationError("Uploaded repository archive is empty")
    if archive_size > MAX_ARCHIVE_BYTES:
        raise RepositoryValidationError("Repository archive exceeds the 100 MiB compressed limit")
    staging_root.mkdir(parents=True, exist_ok=False)
    files_root = staging_root / "files"
    files_root.mkdir()
    exclusions: list[dict] = []
    prepared_files: list[PreparedFile] = []
    seen_paths: set[str] = set()

    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS:
                raise RepositoryValidationError("Repository archive exceeds the 20,000 member limit")
            total_size = sum(info.file_size for info in infos)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise RepositoryValidationError("Repository archive exceeds the 500 MiB expanded limit")

            validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in infos:
                _validate_member_type(info)
                path = _normalized_member_path(info.orig_filename)
                normalized = path.as_posix()
                if normalized in seen_paths:
                    raise RepositoryValidationError("Archive contains duplicate normalized paths")
                seen_paths.add(normalized)
                if info.file_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                    raise RepositoryValidationError("Archive contains a member with an unsafe compression ratio")
                validated.append((info, path))

            for info, path in validated:
                if info.is_dir():
                    continue
                exclusion = _path_exclusion(path)
                if exclusion:
                    exclusions.append({"path": path.as_posix(), "reason": exclusion[0], "security": exclusion[1]})
                    continue
                if info.file_size > MAX_SEARCHABLE_FILE_BYTES:
                    exclusions.append({"path": path.as_posix(), "reason": "file exceeds the 2 MiB searchable limit", "security": False})
                    continue
                raw = archive.read(info)
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    exclusions.append({"path": path.as_posix(), "reason": "text is not valid UTF-8", "security": False})
                    continue
                exclusion = _content_exclusion(raw, text)
                if exclusion:
                    exclusions.append({"path": path.as_posix(), "reason": exclusion[0], "security": exclusion[1]})
                    continue
                chunks = _chunk_source(text)
                if not chunks:
                    exclusions.append({"path": path.as_posix(), "reason": "file contains no searchable text", "security": False})
                    continue
                destination = files_root.joinpath(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                prepared_files.append(
                    PreparedFile(
                        relative_path=path.as_posix(),
                        language=LANGUAGES[Path(path.name).suffix.lower()],
                        size_bytes=len(raw),
                        content_hash=hashlib.sha256(raw).hexdigest(),
                        chunks=chunks,
                    )
                )
    except zipfile.BadZipFile as exc:
        raise RepositoryValidationError("Uploaded file is not a valid ZIP archive") from exc

    if not prepared_files:
        raise RepositoryValidationError("Repository contains no searchable source files after security checks")

    all_chunks = [chunk for prepared in prepared_files for chunk in prepared.chunks]
    for offset in range(0, len(all_chunks), EMBED_BATCH_SIZE):
        batch = all_chunks[offset : offset + EMBED_BATCH_SIZE]
        vectors = embed([chunk.content for chunk in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding service returned an unexpected result count")
        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector

    digest = hashlib.sha256()
    for prepared in sorted(prepared_files, key=lambda item: item.relative_path):
        digest.update(prepared.relative_path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(prepared.content_hash.encode("ascii"))
        digest.update(b"\n")
    return PreparedSnapshot(content_hash=digest.hexdigest(), files=prepared_files, exclusions=exclusions)
