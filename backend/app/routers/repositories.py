"""Local repository snapshot lifecycle and diagnostic search endpoints."""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.document_pipeline import sanitize_filename
from app.models import (
    CodeChunk,
    CodeFile,
    CodeRepository,
    CodeRetrievalLog,
    RepositoryGrant,
    RepositoryStatus,
)
from app.repository_pipeline import (
    MAX_ARCHIVE_BYTES,
    PreparedSnapshot,
    RepositoryValidationError,
    prepare_repository_snapshot,
)
from app.repository_retrieval import retrieve_code
from app.routers.domains import get_owned_domain_or_404
from app.schemas import CodeRepositoryOut, CodeSearchResultOut

router = APIRouter(prefix="/domains", tags=["repositories"], dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)


def _scope_repository_root(scope_id: uuid.UUID) -> Path:
    storage_root = Path(settings.document_storage_path).resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    if storage_root.is_symlink() or not storage_root.is_dir():
        raise HTTPException(status_code=500, detail="Repository storage root is invalid")
    scope_root = storage_root / str(scope_id)
    if scope_root.exists() and scope_root.is_symlink():
        raise HTTPException(status_code=500, detail="Repository scope storage path is invalid")
    result = scope_root / "repositories"
    if result.exists() and (result.is_symlink() or not result.is_dir()):
        raise HTTPException(status_code=500, detail="Repository storage path is invalid")
    result.mkdir(parents=True, exist_ok=True)
    return result


def _repository_or_404(
    db: Session,
    user_id: uuid.UUID,
    scope_id: uuid.UUID,
    repository_id: uuid.UUID,
) -> CodeRepository:
    repository = (
        db.query(CodeRepository)
        .filter_by(id=repository_id, user_id=user_id, scope_id=scope_id)
        .one_or_none()
    )
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found in this scope")
    return repository


async def _store_archive(file: UploadFile, target: Path) -> None:
    filename = file.filename or "repository.zip"
    if Path(filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Repository snapshots must be uploaded as .zip files")
    written = 0
    try:
        with target.open("xb") as destination:
            target.chmod(0o600)
            while True:
                block = await file.read(1024 * 1024)
                if not block:
                    break
                written += len(block)
                if written > MAX_ARCHIVE_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail="Repository archive exceeds the 100 MiB compressed limit",
                    )
                destination.write(block)
        if written == 0:
            raise HTTPException(status_code=400, detail="Uploaded repository archive is empty")
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _safe_display_name(value: str | None, filename: str) -> str:
    candidate = (value or Path(filename).stem or "Repository").strip()
    candidate = re.sub(r"[\x00-\x1f\x7f]", "", candidate).strip()
    if not candidate:
        candidate = "Repository"
    return candidate[:120]


def _safe_repository_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_symlink():
        raise HTTPException(status_code=500, detail="Unsafe repository storage path")
    resolved = candidate.resolve()
    resolved_root = root.resolve()
    if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
        raise HTTPException(status_code=500, detail="Unsafe repository storage path")
    return resolved


def _delete_repository_logs(db: Session, scope_id: uuid.UUID, repository_id: uuid.UUID) -> None:
    repository_key = str(repository_id)
    logs = db.query(CodeRetrievalLog).filter_by(scope_id=scope_id).all()
    for log in logs:
        if repository_key in (log.repository_ids or []):
            db.delete(log)


def _persist_snapshot(db: Session, repository: CodeRepository, prepared: PreparedSnapshot) -> None:
    for prepared_file in prepared.files:
        code_file = CodeFile(
            repository_id=repository.id,
            relative_path=prepared_file.relative_path,
            language=prepared_file.language,
            size_bytes=prepared_file.size_bytes,
            content_hash=prepared_file.content_hash,
        )
        db.add(code_file)
        db.flush()
        for prepared_chunk in prepared_file.chunks:
            db.add(
                CodeChunk(
                    repository_id=repository.id,
                    file_id=code_file.id,
                    scope_id=repository.scope_id,
                    chunk_index=prepared_chunk.chunk_index,
                    start_line=prepared_chunk.start_line,
                    end_line=prepared_chunk.end_line,
                    symbol=prepared_chunk.symbol,
                    content=prepared_chunk.content,
                    search_text=(
                        f"{prepared_file.relative_path}\n{prepared_chunk.symbol or ''}\n{prepared_chunk.content}"
                    ),
                    embedding=prepared_chunk.embedding,
                )
            )


def _apply_metadata(repository: CodeRepository, prepared: PreparedSnapshot, storage_path: Path) -> None:
    repository.content_hash = prepared.content_hash
    repository.storage_path = str(storage_path)
    repository.status = RepositoryStatus.ready
    repository.error = None
    repository.file_count = len(prepared.files)
    repository.skipped_file_count = prepared.skipped_file_count
    repository.security_excluded_count = prepared.security_excluded_count
    repository.chunk_count = prepared.chunk_count
    repository.exclusions = prepared.exclusions


@router.post("/{domain_id}/repositories", response_model=CodeRepositoryOut)
async def upload_repository(
    domain_id: uuid.UUID,
    file: UploadFile,
    name: str | None = Form(None),
    revision_label: str | None = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    archive_filename = sanitize_filename(file.filename or "repository.zip")
    repository = CodeRepository(
        user_id=user.id,
        scope_id=scope.id,
        name=_safe_display_name(name, archive_filename),
        archive_filename=archive_filename,
        revision_label=(revision_label or "").strip()[:120] or None,
        status=RepositoryStatus.validating,
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

    root = _scope_repository_root(scope.id)
    upload_path = root / f".upload-{uuid.uuid4().hex}.zip"
    staging = root / f".staging-{repository.id}-{uuid.uuid4().hex}"
    final_path = root / str(repository.id)
    try:
        await _store_archive(file, upload_path)
        prepared = prepare_repository_snapshot(upload_path, staging)
        repository.status = RepositoryStatus.indexing
        if final_path.exists():
            raise RuntimeError("Repository storage target already exists")
        staging.replace(final_path)
        db.add(RepositoryGrant(repository_id=repository.id, scope_id=scope.id))
        _persist_snapshot(db, repository, prepared)
        _apply_metadata(repository, prepared, final_path)
        db.commit()
        db.refresh(repository)
        return repository
    except Exception as exc:  # noqa: BLE001 - persist a safe, unavailable failure state
        db.rollback()
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(final_path, ignore_errors=True)
        repository = db.get(CodeRepository, repository.id)
        if repository is None:
            raise
        repository.status = RepositoryStatus.failed
        if isinstance(exc, (RepositoryValidationError, HTTPException)):
            repository.error = str(exc.detail if isinstance(exc, HTTPException) else exc)[:2000]
        else:
            logger.exception("Repository indexing failed for %s", repository.id)
            repository.error = "Local indexing failed. Check that the Ollama embedding service is reachable."
        repository.storage_path = ""
        db.commit()
        db.refresh(repository)
        return repository
    finally:
        upload_path.unlink(missing_ok=True)


@router.get("/{domain_id}/repositories", response_model=list[CodeRepositoryOut])
def list_repositories(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    return (
        db.query(CodeRepository)
        .filter_by(user_id=user.id, scope_id=scope.id)
        .order_by(CodeRepository.created_at.desc())
        .all()
    )


@router.post("/{domain_id}/repositories/{repository_id}/replace", response_model=CodeRepositoryOut)
async def replace_repository(
    domain_id: uuid.UUID,
    repository_id: uuid.UUID,
    file: UploadFile,
    revision_label: str | None = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    repository = _repository_or_404(db, user.id, scope.id, repository_id)
    if repository.status != RepositoryStatus.ready:
        raise HTTPException(status_code=409, detail="Only a ready repository snapshot can be replaced")
    root = _scope_repository_root(scope.id)
    old_path = _safe_repository_path(root, repository.storage_path)
    upload_path = root / f".upload-{uuid.uuid4().hex}.zip"
    candidate_id = uuid.uuid4()
    staging = root / f".staging-{candidate_id}-{uuid.uuid4().hex}"
    replacement_path = root / str(candidate_id)

    try:
        await _store_archive(file, upload_path)
        prepared = prepare_repository_snapshot(upload_path, staging)
        staging.replace(replacement_path)
        candidate = CodeRepository(
            id=candidate_id,
            user_id=user.id,
            scope_id=scope.id,
            name=repository.name,
            archive_filename=sanitize_filename(file.filename or "repository.zip"),
            revision_label=(revision_label or "").strip()[:120] or None,
            status=RepositoryStatus.indexing,
        )
        db.add(candidate)
        db.flush()
        db.add(RepositoryGrant(repository_id=candidate.id, scope_id=scope.id))
        _persist_snapshot(db, candidate, prepared)
        _apply_metadata(candidate, prepared, replacement_path)
        _delete_repository_logs(db, scope.id, repository.id)
        db.delete(repository)
        db.commit()
    except RepositoryValidationError as exc:
        db.rollback()
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(replacement_path, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(replacement_path, ignore_errors=True)
        raise
    finally:
        upload_path.unlink(missing_ok=True)

    if old_path != replacement_path:
        try:
            shutil.rmtree(old_path)
        except OSError:
            logger.exception("Could not remove replaced repository snapshot %s", old_path)
    db.refresh(candidate)
    return candidate


@router.get("/{domain_id}/repositories/search", response_model=list[CodeSearchResultOut])
def search_repositories(domain_id: uuid.UUID, q: str, db: Session = Depends(get_db)):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    result = retrieve_code(db, scope.id, q)
    return [
        CodeSearchResultOut(
            repository_id=item.repository.id,
            repository_name=item.repository.name,
            revision_label=item.repository.revision_label,
            snapshot_hash=item.repository.content_hash,
            relative_path=item.file.relative_path,
            start_line=item.chunk.start_line,
            end_line=item.chunk.end_line,
            symbol=item.chunk.symbol,
            content=item.chunk.content,
        )
        for item in result.chunks
    ]


@router.delete("/{domain_id}/repositories/{repository_id}")
def delete_repository(
    domain_id: uuid.UUID,
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    user = get_current_user(db)
    scope = get_owned_domain_or_404(db, domain_id, user.id)
    repository = _repository_or_404(db, user.id, scope.id, repository_id)
    root = _scope_repository_root(scope.id).resolve()
    storage_path = _safe_repository_path(root, repository.storage_path) if repository.storage_path else None
    staged: Path | None = None
    if storage_path and storage_path.exists():
        resolved = storage_path.resolve()
        deleting_root = root / ".deleting"
        deleting_root.mkdir(exist_ok=True)
        staged = deleting_root / f"{repository.id}-{uuid.uuid4().hex}"
        resolved.replace(staged)
    try:
        repository.status = RepositoryStatus.deleting
        _delete_repository_logs(db, scope.id, repository.id)
        db.delete(repository)
        db.commit()
    except Exception:
        db.rollback()
        if staged and staged.exists() and storage_path and not storage_path.exists():
            staged.replace(storage_path)
        raise

    cleanup_complete = True
    if staged:
        try:
            shutil.rmtree(staged)
        except OSError:
            cleanup_complete = False
            logger.exception("Could not remove staged repository directory %s", staged)
    return {"ok": True, "storage_cleanup_complete": cleanup_complete}
