from types import SimpleNamespace
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
import pytest

from app import document_pipeline
from app.document_pipeline import Page, pdf_to_markdown
from app.models import Document, DocumentStatus
from app.routers import documents
from app.schemas import DocumentOut


def test_pdf_to_markdown_preserves_page_boundaries(monkeypatch):
    monkeypatch.setattr(
        document_pipeline,
        "extract_pages",
        lambda _data, source_type: [
            Page(text="First page text.\nSecond line.", page_number=1),
            Page(text="Second page text.", page_number=2),
        ]
        if source_type == "pdf"
        else [],
    )

    markdown = pdf_to_markdown(b"pdf bytes are mocked", "Quarterly Report.pdf")

    assert markdown == (
        "# Quarterly Report\n\n"
        "## Page 1\n\n"
        "First page text.\nSecond line.\n\n"
        "## Page 2\n\n"
        "Second page text.\n"
    )


def test_pdf_to_markdown_rejects_image_only_pdf(monkeypatch):
    monkeypatch.setattr(document_pipeline, "extract_pages", lambda _data, _source_type: [])

    with pytest.raises(ValueError, match="require OCR"):
        pdf_to_markdown(b"pdf bytes are mocked", "scan.pdf")


def test_document_response_discovers_stored_markdown_in_same_scope_directory(tmp_path):
    document_id = uuid.uuid4()
    source = tmp_path / "scope" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"fake PDF")
    document = Document(
        id=document_id,
        user_id=uuid.uuid4(),
        scope_id=uuid.uuid4(),
        filename="Paper.pdf",
        sanitized_filename="Paper.pdf",
        content_hash="hash",
        source_type="pdf",
        storage_path=str(source),
        folder_path="Research/Papers",
        tags=["research"],
        status=DocumentStatus.ready,
        error=None,
        chunk_count=2,
        version=1,
        created_at=datetime.now(timezone.utc),
    )
    (source.parent / f"{document_id}_derived.md").write_text("# Paper", encoding="utf-8")

    response = DocumentOut.model_validate(document)

    assert response.folder_path == "Research/Papers"
    assert response.markdown_available is True
    assert response.markdown_filename == "Paper.md"


def test_repeated_pdf_page_noise_is_removed():
    pages = [
        Page(text=f"Repeated header\nUnique page {number}\nRepeated footer", page_number=number)
        for number in range(1, 6)
    ]

    cleaned = document_pipeline._strip_repeated_noise(pages)

    assert all("Repeated header" not in page.text for page in cleaned)
    assert all("Repeated footer" not in page.text for page in cleaned)
    assert [page.text for page in cleaned] == [f"Unique page {number}" for number in range(1, 6)]


def test_export_endpoint_returns_markdown_attachment(tmp_path, monkeypatch):
    scope_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source = tmp_path / "scope" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(b"small fake PDF")
    document = SimpleNamespace(
        id=document_id,
        scope_id=scope_id,
        source_type="pdf",
        storage_path=str(source),
        filename="Source Document.pdf",
        sanitized_filename="Source_Document.pdf",
    )
    db = SimpleNamespace(get=lambda _model, requested_id: document if requested_id == document_id else None)
    monkeypatch.setattr(documents.settings, "document_storage_path", str(tmp_path))
    monkeypatch.setattr(documents, "pdf_to_markdown", lambda _data, _filename: "# Source Document\n")

    response = documents.export_document_markdown(scope_id, document_id, db)

    assert response.body == b"# Source Document\n"
    assert response.media_type == "text/markdown; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="Source_Document.md"'
    assert (source.parent / f"{document_id}_derived.md").read_text(encoding="utf-8") == "# Source Document\n"


def test_create_markdown_persists_companion_without_creating_another_document(tmp_path, monkeypatch):
    scope_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source = tmp_path / "scope" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(b"small fake PDF")
    document = SimpleNamespace(
        id=document_id,
        scope_id=scope_id,
        source_type="pdf",
        storage_path=str(source),
        filename="Source Document.pdf",
        sanitized_filename="Source_Document.pdf",
        folder_path="Research/Papers",
    )
    db = SimpleNamespace(get=lambda _model, requested_id: document if requested_id == document_id else None)
    monkeypatch.setattr(documents.settings, "document_storage_path", str(tmp_path))
    monkeypatch.setattr(documents, "pdf_to_markdown", lambda _data, _filename: "# Stored copy\n")

    result = documents.create_document_markdown(scope_id, document_id, db)

    assert result is document
    assert document.folder_path == "Research/Papers"
    assert (source.parent / f"{document_id}_derived.md").read_text(encoding="utf-8") == "# Stored copy\n"


def test_preview_supports_source_text_and_stored_markdown(tmp_path, monkeypatch):
    scope_id = uuid.uuid4()
    text_id = uuid.uuid4()
    text_source = tmp_path / "scope" / "notes.txt"
    text_source.parent.mkdir()
    text_source.write_text("plain notes", encoding="utf-8")
    text_document = SimpleNamespace(
        id=text_id,
        scope_id=scope_id,
        source_type="txt",
        storage_path=str(text_source),
        filename="notes.txt",
        sanitized_filename="notes.txt",
    )
    db = SimpleNamespace(get=lambda _model, requested_id: text_document if requested_id == text_id else None)
    monkeypatch.setattr(documents.settings, "document_storage_path", str(tmp_path))

    preview = documents.preview_document(scope_id, text_id, "source", db)

    assert preview.content == "plain notes"
    assert preview.format == "text"
    assert preview.truncated is False

    pdf_id = uuid.uuid4()
    pdf_source = tmp_path / "scope" / "paper.pdf"
    pdf_source.write_bytes(b"fake PDF")
    markdown_path = pdf_source.parent / f"{pdf_id}_derived.md"
    markdown_path.write_text("# Paper\n\nStored text", encoding="utf-8")
    pdf_document = SimpleNamespace(
        id=pdf_id,
        scope_id=scope_id,
        source_type="pdf",
        storage_path=str(pdf_source),
        filename="paper.pdf",
        sanitized_filename="paper.pdf",
    )
    db.get = lambda _model, requested_id: pdf_document if requested_id == pdf_id else None

    markdown_preview = documents.preview_document(scope_id, pdf_id, "markdown", db)

    assert markdown_preview.filename == "paper.md"
    assert markdown_preview.content == "# Paper\n\nStored text"
    assert markdown_preview.format == "markdown"
    assert markdown_preview.markdown_copy is True


def test_delete_document_removes_source_and_markdown_companion(tmp_path):
    scope_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source = tmp_path / "scope" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"fake PDF")
    markdown_path = source.parent / f"{document_id}_derived.md"
    markdown_path.write_text("# Paper", encoding="utf-8")
    document = SimpleNamespace(
        id=document_id,
        scope_id=scope_id,
        source_type="pdf",
        storage_path=str(source),
    )

    class FakeDb:
        def get(self, _model, requested_id):
            return document if requested_id == document_id else None

        def delete(self, deleted):
            assert deleted is document

        def commit(self):
            pass

    result = documents.delete_document(scope_id, document_id, FakeDb())

    assert result == {"ok": True}
    assert not source.exists()
    assert not markdown_path.exists()


def test_export_endpoint_rejects_storage_path_outside_root(tmp_path, monkeypatch):
    scope_id = uuid.uuid4()
    document_id = uuid.uuid4()
    document = SimpleNamespace(
        id=document_id,
        scope_id=scope_id,
        source_type="pdf",
        storage_path=str(tmp_path.parent / "outside.pdf"),
        filename="outside.pdf",
        sanitized_filename="outside.pdf",
    )
    db = SimpleNamespace(get=lambda _model, _requested_id: document)
    monkeypatch.setattr(documents.settings, "document_storage_path", str(tmp_path))

    with pytest.raises(HTTPException, match="Unsafe document storage path") as exc_info:
        documents.export_document_markdown(scope_id, document_id, db)

    assert exc_info.value.status_code == 500
