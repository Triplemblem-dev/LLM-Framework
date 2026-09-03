import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.document_pipeline import (
    detect_source_type,
    hash_bytes,
    pdf_to_markdown,
    process_document,
    sanitize_filename,
)
from app.document_organizer import (
    DocumentOrganizerConflict,
    DocumentOrganizerError,
    DocumentOrganizerModelError,
    apply_organization,
    preview_organization,
)
from app.models import Document, DocumentStatus
from app.optimizer.activity import OllamaBusyError
from app.prompt_assembly import sharing_siblings
from app.routers.domains import get_domain_or_404
from app.schemas import (
    DocumentOrganizationApplyRequest,
    DocumentOrganizationPreviewOut,
    DocumentOrganizationPreviewRequest,
    DocumentOut,
    DocumentPreviewOut,
    InheritedDocumentOut,
)

router = APIRouter(prefix="/domains", tags=["documents"], dependencies=[Depends(require_auth)])


def _storage_dir(scope_id: uuid.UUID) -> Path:
    path = Path(settings.document_storage_path) / str(scope_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_document_or_404(db: Session, domain_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.scope_id != domain_id:
        raise HTTPException(status_code=404, detail="Document not found in this scope")
    return doc


def _validated_source_path(doc: Document) -> Path:
    storage_root = Path(settings.document_storage_path).resolve()
    source = Path(doc.storage_path).resolve()
    try:
        source.relative_to(storage_root)
    except ValueError:
        raise HTTPException(status_code=500, detail="Unsafe document storage path") from None
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Stored document file was not found")
    if source.stat().st_size > settings.document_max_bytes:
        raise HTTPException(status_code=400, detail="Stored document exceeds the maximum document size")
    return source


def _markdown_path(doc: Document) -> Path:
    source = _validated_source_path(doc)
    return source.parent / f"{doc.id}_derived.md"


def _markdown_filename(doc: Document) -> str:
    return f"{Path(doc.sanitized_filename).stem or 'document'}.md"


def _convert_pdf(doc: Document) -> tuple[str, Path]:
    if doc.source_type != "pdf":
        raise HTTPException(status_code=400, detail="Only PDF documents can be converted to Markdown")
    source = _validated_source_path(doc)
    try:
        markdown = pdf_to_markdown(source.read_bytes(), doc.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=422, detail="The PDF could not be converted to Markdown") from None

    destination = source.parent / f"{doc.id}_derived.md"
    temporary = source.parent / f".{doc.id}_{uuid.uuid4().hex}.md.tmp"
    try:
        temporary.write_text(markdown, encoding="utf-8")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return markdown, destination


def _preview(content: str, *, filename: str, source_type: str, markdown_copy: bool) -> DocumentPreviewOut:
    character_count = len(content)
    limit = settings.document_preview_max_characters
    return DocumentPreviewOut(
        filename=filename,
        source_type=source_type,
        format="markdown" if source_type in {"md", "markdown", "pdf"} or markdown_copy else "text",
        content=content[:limit],
        character_count=character_count,
        truncated=character_count > limit,
        markdown_copy=markdown_copy,
    )


@router.post("/{domain_id}/documents", response_model=DocumentOut)
async def upload_document(domain_id: uuid.UUID, file: UploadFile, db: Session = Depends(get_db)):
    user = get_current_user(db)
    scope = get_domain_or_404(db, domain_id)

    try:
        source_type = detect_source_type(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > settings.document_max_bytes:
        raise HTTPException(status_code=400, detail="File exceeds the maximum upload size")

    sanitized = sanitize_filename(file.filename or "upload")
    content_hash = hash_bytes(data)

    document = Document(
        user_id=user.id,
        scope_id=scope.id,
        filename=file.filename or sanitized,
        sanitized_filename=sanitized,
        content_hash=content_hash,
        source_type=source_type,
        storage_path="",
        status=DocumentStatus.pending,
    )
    db.add(document)
    db.flush()

    dest = _storage_dir(scope.id) / f"{document.id}_{sanitized}"
    dest.write_bytes(data)
    document.storage_path = str(dest)
    db.commit()
    db.refresh(document)

    process_document(db, document, data)
    db.refresh(document)
    return document


@router.get("/{domain_id}/documents", response_model=list[DocumentOut])
def list_documents(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    get_domain_or_404(db, domain_id)
    return (
        db.query(Document)
        .filter_by(scope_id=domain_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.post("/{domain_id}/documents/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(
    domain_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Retry extraction and indexing without requiring another upload."""
    doc = get_document_or_404(db, domain_id, document_id)
    source = _validated_source_path(doc)
    process_document(db, doc, source.read_bytes())
    db.refresh(doc)
    return doc


@router.get("/{domain_id}/documents/inherited", response_model=list[InheritedDocumentOut])
def list_inherited_documents(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    """Read-only view of documents visible to this scope via inheritance/sibling-sharing but
    owned elsewhere - mirrors prompt_assembly.approved_scope_ids minus the scope itself, so this
    list always matches what retrieval can actually see."""
    scope = get_domain_or_404(db, domain_id)
    other_scopes = []
    if scope.parent_domain_id is not None and scope.inheritance.value == "inherited":
        other_scopes.append(scope.parent)
    other_scopes += sharing_siblings(db, scope)
    if not other_scopes:
        return []

    results = []
    for other in other_scopes:
        docs = db.query(Document).filter_by(scope_id=other.id).order_by(Document.created_at.desc()).all()
        for doc in docs:
            results.append(
                InheritedDocumentOut(
                    id=doc.id,
                    filename=doc.filename,
                    source_type=doc.source_type,
                    folder_path=doc.folder_path,
                    tags=doc.tags,
                    version=doc.version,
                    status=doc.status,
                    error=doc.error,
                    chunk_count=doc.chunk_count,
                    created_at=doc.created_at,
                    markdown_available=doc.markdown_available,
                    markdown_filename=doc.markdown_filename,
                    scope_id=other.id,
                    scope_name=other.name,
                )
            )
    return results


@router.post("/{domain_id}/documents/organize/preview", response_model=DocumentOrganizationPreviewOut)
def preview_document_organization(
    domain_id: uuid.UUID,
    body: DocumentOrganizationPreviewRequest,
    db: Session = Depends(get_db),
):
    scope = get_domain_or_404(db, domain_id)
    try:
        preview = preview_organization(db, scope.id, scope.name, body.model_tag)
    except OllamaBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except DocumentOrganizerModelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except DocumentOrganizerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"Document organizer model failed: {exc}") from None
    return DocumentOrganizationPreviewOut(
        model_tag=preview.model_tag,
        document_set_hash=preview.document_set_hash,
        suggestions=preview.suggestions,
        warnings=preview.warnings,
    )


@router.post("/{domain_id}/documents/organize/apply", response_model=list[DocumentOut])
def apply_document_organization(
    domain_id: uuid.UUID,
    body: DocumentOrganizationApplyRequest,
    db: Session = Depends(get_db),
):
    scope = get_domain_or_404(db, domain_id)
    try:
        return apply_organization(db, scope.id, body.document_set_hash, body.suggestions)
    except DocumentOrganizerConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except DocumentOrganizerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/{domain_id}/documents/{document_id}/markdown", response_model=DocumentOut)
def create_document_markdown(
    domain_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Persist a Markdown companion beside the source while keeping one retrieval record."""
    doc = get_document_or_404(db, domain_id, document_id)
    _convert_pdf(doc)
    return doc


@router.get("/{domain_id}/documents/{document_id}/preview", response_model=DocumentPreviewOut)
def preview_document(
    domain_id: uuid.UUID,
    document_id: uuid.UUID,
    variant: str = Query(default="source", pattern=r"^(source|markdown)$"),
    db: Session = Depends(get_db),
):
    doc = get_document_or_404(db, domain_id, document_id)
    source = _validated_source_path(doc)

    if variant == "markdown":
        if doc.source_type != "pdf":
            raise HTTPException(status_code=400, detail="This document has no generated Markdown copy")
        markdown_path = _markdown_path(doc)
        if not markdown_path.is_file():
            raise HTTPException(status_code=404, detail="Convert this PDF to Markdown before viewing its copy")
        return _preview(
            markdown_path.read_text(encoding="utf-8"),
            filename=_markdown_filename(doc),
            source_type="md",
            markdown_copy=True,
        )

    if doc.source_type == "pdf":
        markdown_path = _markdown_path(doc)
        if markdown_path.is_file():
            content = markdown_path.read_text(encoding="utf-8")
        else:
            try:
                content = pdf_to_markdown(source.read_bytes(), doc.filename)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None
            except Exception:
                raise HTTPException(status_code=422, detail="The PDF could not be previewed") from None
    else:
        content = source.read_text(encoding="utf-8", errors="replace")
    return _preview(
        content,
        filename=doc.filename,
        source_type=doc.source_type,
        markdown_copy=False,
    )


@router.get("/{domain_id}/documents/{document_id}/markdown")
def export_document_markdown(
    domain_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    doc = get_document_or_404(db, domain_id, document_id)
    if doc.source_type != "pdf":
        raise HTTPException(status_code=400, detail="Only PDF documents can be exported to Markdown")
    markdown_path = _markdown_path(doc)
    if markdown_path.is_file():
        markdown = markdown_path.read_text(encoding="utf-8")
    else:
        markdown, _ = _convert_pdf(doc)
    filename = _markdown_filename(doc)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{domain_id}/documents/{document_id}")
def delete_document(domain_id: uuid.UUID, document_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, domain_id, document_id)
    storage_path = Path(doc.storage_path) if doc.storage_path else None
    markdown_path = storage_path.parent / f"{doc.id}_derived.md" if storage_path else None
    db.delete(doc)
    db.commit()
    if storage_path and storage_path.exists():
        storage_path.unlink()
    if markdown_path and markdown_path.exists():
        markdown_path.unlink()
    return {"ok": True}
