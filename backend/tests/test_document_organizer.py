from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest

from app import document_organizer
from app.document_organizer import (
    DocumentOrganizerConflict,
    DocumentOrganizerError,
    DocumentOrganizerModelError,
    apply_organization,
    document_set_hash,
    normalize_folder_path,
    normalize_tags,
    preview_organization,
)


def make_document(filename: str, content_hash: str = "a" * 64):
    return SimpleNamespace(
        id=uuid.uuid4(),
        filename=filename,
        content_hash=content_hash,
        source_type="pdf",
        folder_path="",
        tags=[],
    )


def test_folder_and_tag_validation():
    assert normalize_folder_path(" /Finance\\Contracts/ ") == "Finance/Contracts"
    assert normalize_tags(["Contract", "contract", " 2026 ", ""]) == ["Contract", "2026"]

    with pytest.raises(DocumentOrganizerError, match="at most 4 levels"):
        normalize_folder_path("one/two/three/four/five")
    with pytest.raises(DocumentOrganizerError, match="cannot contain"):
        normalize_folder_path("Finance/../Private")
    with pytest.raises(DocumentOrganizerError, match="at most 6 tags"):
        normalize_tags([str(index) for index in range(7)])


def test_recommended_model_uses_largest_non_embedding_model(monkeypatch):
    monkeypatch.setattr(document_organizer.settings, "embedding_model", "nomic-embed-text")
    monkeypatch.setattr(
        document_organizer,
        "list_installed_models",
        lambda: [
            {"model": "nomic-embed-text", "size": 9_000},
            {"model": "small-chat", "size": 2_000},
            {"model": "large-chat", "size": 8_000},
        ],
    )

    assert document_organizer._select_model(None) == "large-chat"
    assert document_organizer._select_model("small-chat") == "small-chat"
    with pytest.raises(DocumentOrganizerError, match="embedding model"):
        document_organizer._select_model("nomic-embed-text")


def test_preview_requires_complete_validated_model_output(monkeypatch):
    first = make_document("Contract.pdf")
    second = make_document("Invoice.pdf", "b" * 64)
    documents = [first, second]
    monkeypatch.setattr(document_organizer, "_documents", lambda _db, _scope_id: documents)
    monkeypatch.setattr(document_organizer, "_select_model", lambda _requested: "large-chat")
    monkeypatch.setattr(
        document_organizer,
        "_inventory",
        lambda _db, _documents: ([{"document_id": str(item.id)} for item in documents], []),
    )
    monkeypatch.setattr(
        document_organizer,
        "chat_structured",
        lambda _model, _messages, _schema: {
            "documents": [
                {
                    "document_id": str(first.id),
                    "folder_path": "Finance/Contracts",
                    "tags": ["contract", "legal"],
                    "reason": "A contract.",
                },
                {
                    "document_id": str(second.id),
                    "folder_path": "Finance/Invoices",
                    "tags": ["invoice", "finance"],
                    "reason": "An invoice.",
                },
            ]
        },
    )

    preview = preview_organization(MagicMock(), uuid.uuid4(), "Finance", None)

    assert preview.model_tag == "large-chat"
    assert preview.document_set_hash == document_set_hash(documents)
    assert [item["filename"] for item in preview.suggestions] == ["Contract.pdf", "Invoice.pdf"]

    monkeypatch.setattr(
        document_organizer,
        "chat_structured",
        lambda _model, _messages, _schema: {"documents": []},
    )
    with pytest.raises(DocumentOrganizerModelError, match="every document"):
        preview_organization(MagicMock(), uuid.uuid4(), "Finance", None)


def test_apply_is_stale_safe_and_updates_only_after_validation(monkeypatch):
    first = make_document("Contract.pdf")
    second = make_document("Invoice.pdf", "b" * 64)
    documents = [first, second]
    monkeypatch.setattr(document_organizer, "_documents", lambda _db, _scope_id: documents)
    db = MagicMock()
    suggestions = [
        SimpleNamespace(document_id=first.id, folder_path="Finance/Contracts", tags=["legal"]),
        SimpleNamespace(document_id=second.id, folder_path="Finance/Invoices", tags=["billing"]),
    ]

    with pytest.raises(DocumentOrganizerConflict, match="changed after this preview"):
        apply_organization(db, uuid.uuid4(), "0" * 64, suggestions)
    db.commit.assert_not_called()

    result = apply_organization(db, uuid.uuid4(), document_set_hash(documents), suggestions)

    assert first.folder_path == "Finance/Contracts"
    assert first.tags == ["legal"]
    assert second.folder_path == "Finance/Invoices"
    assert result == documents
    db.commit.assert_called_once()
