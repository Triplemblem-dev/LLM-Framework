from types import SimpleNamespace
import uuid

import httpx
import pytest

from app import document_pipeline, ollama_client
from app.models import DocumentStatus
from app.routers import documents


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.request = httpx.Request("POST", "http://ollama:11434/api/embed")

    def raise_for_status(self):
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request)
            raise httpx.HTTPStatusError("embedding request failed", request=self.request, response=response)

    def json(self):
        return self.payload


def test_embed_reports_missing_model_as_actionable_indexing_error(monkeypatch):
    monkeypatch.setattr(ollama_client.httpx, "post", lambda *_args, **_kwargs: FakeResponse({}, 404))
    monkeypatch.setattr(ollama_client.settings, "embedding_model", "nomic-embed-text")

    with pytest.raises(ollama_client.EmbeddingError, match="not installed.*Retry indexing"):
        ollama_client.embed(["Local document text"])


def test_embed_rejects_incomplete_response(monkeypatch):
    monkeypatch.setattr(
        ollama_client.httpx,
        "post",
        lambda *_args, **_kwargs: FakeResponse({"embeddings": [[0.0, 1.0]]}),
    )
    monkeypatch.setattr(ollama_client.settings, "embedding_dimensions", 2)

    with pytest.raises(ollama_client.EmbeddingError, match="incomplete"):
        ollama_client.embed(["first", "second"])


def test_process_document_replaces_existing_chunks_on_success(monkeypatch):
    document = SimpleNamespace(
        id=uuid.uuid4(),
        scope_id=uuid.uuid4(),
        source_type="md",
        status=DocumentStatus.failed,
        error="previous error",
        chunk_count=0,
    )

    class FakeQuery:
        def __init__(self):
            self.deleted = False

        def filter_by(self, **kwargs):
            assert kwargs == {"document_id": document.id}
            return self

        def delete(self, synchronize_session=False):
            assert synchronize_session is False
            self.deleted = True

    class FakeDb:
        def __init__(self):
            self.query_result = FakeQuery()
            self.added = []
            self.commits = 0

        def query(self, model):
            assert model is document_pipeline.DocumentChunk
            return self.query_result

        def add(self, chunk):
            self.added.append(chunk)

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError("successful indexing must not roll back")

    db = FakeDb()
    monkeypatch.setattr(document_pipeline, "embed", lambda texts: [[0.0] * 768 for _ in texts])

    document_pipeline.process_document(db, document, b"# Notes\n\nThe model should retrieve this text.")

    assert db.query_result.deleted is True
    assert len(db.added) == 1
    assert document.status == DocumentStatus.ready
    assert document.chunk_count == 1
    assert document.error is None
    assert db.commits == 1


def test_reindex_document_uses_saved_source(tmp_path, monkeypatch):
    scope_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source = tmp_path / str(scope_id) / "notes.md"
    source.parent.mkdir()
    source.write_bytes(b"# Saved notes\n\nReusable content")
    document = SimpleNamespace(id=document_id, scope_id=scope_id, storage_path=str(source))

    class FakeDb:
        def get(self, _model, requested_id):
            return document if requested_id == document_id else None

        def refresh(self, refreshed):
            assert refreshed is document

    processed = []
    monkeypatch.setattr(documents.settings, "document_storage_path", str(tmp_path))
    monkeypatch.setattr(documents, "process_document", lambda _db, doc, data: processed.append((doc, data)))

    result = documents.reindex_document(scope_id, document_id, FakeDb())

    assert result is document
    assert processed == [(document, b"# Saved notes\n\nReusable content")]
