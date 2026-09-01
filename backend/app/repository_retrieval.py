"""Exact-scope, local-only hybrid retrieval for validated repository snapshots."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CodeChunk, CodeFile, CodeRepository, RepositoryGrant, RepositoryStatus
from app.ollama_client import embed

RESULT_LIMIT = min(settings.repository_result_limit, 8)
CHARACTER_LIMIT = min(settings.repository_character_limit, 12_000)
SEMANTIC_CANDIDATE_LIMIT = 20
LEXICAL_CANDIDATE_LIMIT = 40
MAX_SEMANTIC_DISTANCE = 0.65
logger = logging.getLogger(__name__)


@dataclass
class RetrievedCodeChunk:
    chunk: CodeChunk
    file: CodeFile
    repository: CodeRepository


@dataclass
class CodeRetrievalResult:
    chunks: list[RetrievedCodeChunk] = field(default_factory=list)
    repository_ids: list[uuid.UUID] = field(default_factory=list)
    repositories_available: bool = False
    error: str | None = None


def granted_repositories(db: Session, scope_id: uuid.UUID) -> list[CodeRepository]:
    return (
        db.query(CodeRepository)
        .join(RepositoryGrant, RepositoryGrant.repository_id == CodeRepository.id)
        .filter(
            RepositoryGrant.scope_id == scope_id,
            CodeRepository.scope_id == scope_id,
            CodeRepository.status == RepositoryStatus.ready,
        )
        .order_by(CodeRepository.created_at, CodeRepository.id)
        .all()
    )


def _row(chunk: CodeChunk, file: CodeFile, repository: CodeRepository) -> RetrievedCodeChunk:
    return RetrievedCodeChunk(chunk=chunk, file=file, repository=repository)


def retrieve_code(db: Session, scope_id: uuid.UUID, query_text: str) -> CodeRetrievalResult:
    repositories = granted_repositories(db, scope_id)
    result = CodeRetrievalResult(
        repository_ids=[repository.id for repository in repositories],
        repositories_available=bool(repositories),
    )
    query = query_text.strip()
    if not query or not repositories:
        return result

    repository_ids = result.repository_ids
    try:
        vector = embed([query])[0]
    except Exception:  # noqa: BLE001 - retrieval must fail closed if local embeddings are unavailable
        logger.exception("Local repository query embedding failed for scope %s", scope_id)
        result.error = "Local repository retrieval failed"
        return result
    distance = CodeChunk.embedding.cosine_distance(vector).label("distance")
    semantic_rows = (
        db.query(CodeChunk, CodeFile, CodeRepository, distance)
        .join(CodeFile, CodeChunk.file_id == CodeFile.id)
        .join(CodeRepository, CodeChunk.repository_id == CodeRepository.id)
        .filter(
            CodeChunk.scope_id == scope_id,
            CodeChunk.repository_id.in_(repository_ids),
            CodeRepository.status == RepositoryStatus.ready,
        )
        .order_by(distance, CodeChunk.id)
        .limit(SEMANTIC_CANDIDATE_LIMIT)
        .all()
    )

    tokens = list(dict.fromkeys(re.findall(r"[A-Za-z_$][A-Za-z0-9_$.-]{2,}", query)))[:8]
    lexical_rows = []
    if tokens:
        predicates = []
        for token in tokens:
            escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            predicates.extend(
                [
                    CodeFile.relative_path.ilike(pattern, escape="\\"),
                    CodeChunk.symbol.ilike(pattern, escape="\\"),
                    CodeChunk.content.ilike(pattern, escape="\\"),
                ]
            )
        lexical_rows = (
            db.query(CodeChunk, CodeFile, CodeRepository)
            .join(CodeFile, CodeChunk.file_id == CodeFile.id)
            .join(CodeRepository, CodeChunk.repository_id == CodeRepository.id)
            .filter(
                CodeChunk.scope_id == scope_id,
                CodeChunk.repository_id.in_(repository_ids),
                CodeRepository.status == RepositoryStatus.ready,
                or_(*predicates),
            )
            .order_by(CodeFile.relative_path, CodeChunk.start_line, CodeChunk.id)
            .limit(LEXICAL_CANDIDATE_LIMIT)
            .all()
        )

    candidates: dict[uuid.UUID, RetrievedCodeChunk] = {}
    scores: dict[uuid.UUID, float] = {}
    for rank, (chunk, file, repository, semantic_distance) in enumerate(semantic_rows):
        if semantic_distance is None or semantic_distance > MAX_SEMANTIC_DISTANCE:
            continue
        candidates[chunk.id] = _row(chunk, file, repository)
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (rank + 1)

    lowered_tokens = [token.lower() for token in tokens]
    for chunk, file, repository in lexical_rows:
        candidates[chunk.id] = _row(chunk, file, repository)
        path = file.relative_path.lower()
        symbol = (chunk.symbol or "").lower()
        content = chunk.content.lower()
        exact_score = 0.0
        for token in lowered_tokens:
            if token in path:
                exact_score += 50.0
            if token == symbol:
                exact_score += 100.0
            elif token in symbol:
                exact_score += 60.0
            exact_score += min(content.count(token), 5) * 8.0
        scores[chunk.id] = scores.get(chunk.id, 0.0) + exact_score

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            -scores[item.chunk.id],
            item.file.relative_path,
            item.chunk.start_line,
            str(item.chunk.id),
        ),
    )
    selected: list[RetrievedCodeChunk] = []
    used_chars = 0
    for item in ordered:
        strongly_overlaps = False
        for existing in selected:
            if existing.file.id != item.file.id:
                continue
            overlap = max(
                0,
                min(existing.chunk.end_line, item.chunk.end_line)
                - max(existing.chunk.start_line, item.chunk.start_line)
                + 1,
            )
            shorter = min(
                existing.chunk.end_line - existing.chunk.start_line + 1,
                item.chunk.end_line - item.chunk.start_line + 1,
            )
            if shorter and overlap / shorter >= 0.5:
                strongly_overlaps = True
                break
        if strongly_overlaps:
            continue
        if selected and used_chars + len(item.chunk.content) > CHARACTER_LIMIT:
            continue
        selected.append(item)
        used_chars += len(item.chunk.content)
        if len(selected) >= RESULT_LIMIT:
            break
    result.chunks = selected
    return result


def code_citation(item: RetrievedCodeChunk, scope_name: str) -> dict:
    return {
        "source_type": "repository",
        "document_id": None,
        "document_name": None,
        "scope_id": str(item.chunk.scope_id),
        "scope_name": scope_name,
        "heading": None,
        "page_number": None,
        "chunk_index": item.chunk.chunk_index,
        "repository_id": str(item.repository.id),
        "repository_name": item.repository.name,
        "revision_label": item.repository.revision_label,
        "snapshot_hash": item.repository.content_hash,
        "relative_path": item.file.relative_path,
        "start_line": item.chunk.start_line,
        "end_line": item.chunk.end_line,
    }
