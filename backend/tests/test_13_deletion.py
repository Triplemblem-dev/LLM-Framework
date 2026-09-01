"""Destructive-action regression tests: ownership, cascades, and stored-file cleanup."""

from pathlib import Path
import uuid

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Conversation,
    Document,
    Memory,
    Message,
    MessageRole,
    RetrievalLog,
    User,
)
from app.seed import DEFAULT_USER_EMAIL


def _seed_conversation(domain_id, title="Deletion test") -> dict:
    scope_id = uuid.UUID(str(domain_id))
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=DEFAULT_USER_EMAIL).one()
        conversation = Conversation(user_id=user.id, domain_id=scope_id, title=title)
        db.add(conversation)
        db.flush()
        message = Message(
            conversation_id=conversation.id,
            role=MessageRole.user,
            content="Temporary message",
            citations=[],
        )
        retrieval = RetrievalLog(
            user_id=user.id,
            scope_id=scope_id,
            conversation_id=conversation.id,
            query_text="Temporary query",
            approved_scope_ids=[str(scope_id)],
            retrieved_chunk_ids=[],
        )
        memory = Memory(
            user_id=user.id,
            scope_id=scope_id,
            conversation_id=conversation.id,
            content="Saved independently from the conversation",
        )
        db.add_all([message, retrieval, memory])
        db.commit()
        return {
            "conversation_id": conversation.id,
            "message_id": message.id,
            "retrieval_id": retrieval.id,
            "memory_id": memory.id,
        }


def test_delete_conversation_cascades_messages_and_logs_but_preserves_saved_memory(
    client, domain_factory
):
    domain = domain_factory("Delete conversation scope")
    seeded = _seed_conversation(domain["id"])

    response = client.delete(
        f"/domains/{domain['id']}/conversations/{seeded['conversation_id']}"
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(Conversation, seeded["conversation_id"]) is None
        assert db.get(Message, seeded["message_id"]) is None
        assert db.get(RetrievalLog, seeded["retrieval_id"]) is None
        memory = db.get(Memory, seeded["memory_id"])
        assert memory is not None
        assert memory.conversation_id is None


def test_delete_conversation_through_wrong_scope_is_rejected(client, domain_factory):
    alpha = domain_factory("Delete conversation owner")
    beta = domain_factory("Delete conversation foreign scope")
    seeded = _seed_conversation(alpha["id"])

    response = client.delete(
        f"/domains/{beta['id']}/conversations/{seeded['conversation_id']}"
    )
    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.get(Conversation, seeded["conversation_id"]) is not None


def test_delete_subdomain_removes_owned_rows_and_document_files_but_keeps_parent(
    client, domain_factory
):
    parent = domain_factory("Delete child parent")
    child = domain_factory("Delete child", parent_id=parent["id"])
    seeded = _seed_conversation(child["id"])

    storage_root = Path(settings.document_storage_path).resolve()
    scope_dir = storage_root / child["id"]
    scope_dir.mkdir(parents=True, exist_ok=True)
    stored_file = scope_dir / "deletion-test.txt"
    stored_file.write_text("private deletion test", encoding="utf-8")

    with SessionLocal() as db:
        user = db.query(User).filter_by(email=DEFAULT_USER_EMAIL).one()
        document = Document(
            user_id=user.id,
            scope_id=uuid.UUID(child["id"]),
            filename="deletion-test.txt",
            sanitized_filename="deletion-test.txt",
            content_hash="test-hash",
            source_type="txt",
            storage_path=str(stored_file),
        )
        db.add(document)
        db.commit()
        document_id = document.id

    response = client.delete(f"/domains/{child['id']}")
    assert response.status_code == 200
    assert response.json()["deleted_scope_count"] == 1
    assert response.json()["storage_cleanup_complete"] is True

    with SessionLocal() as db:
        from app.models import Domain

        assert db.get(Domain, parent["id"]) is not None
        assert db.get(Domain, child["id"]) is None
        assert db.get(Conversation, seeded["conversation_id"]) is None
        assert db.get(Message, seeded["message_id"]) is None
        assert db.get(Memory, seeded["memory_id"]) is None
        assert db.get(Document, document_id) is None
    assert not scope_dir.exists()


def test_delete_domain_cascades_to_subdomains_and_their_conversations(client, domain_factory):
    parent = domain_factory("Delete domain tree")
    child = domain_factory("Delete domain tree child", parent_id=parent["id"])
    seeded = _seed_conversation(child["id"])

    response = client.delete(f"/domains/{parent['id']}")
    assert response.status_code == 200
    assert response.json()["deleted_scope_count"] == 2

    with SessionLocal() as db:
        from app.models import Domain

        assert db.get(Domain, parent["id"]) is None
        assert db.get(Domain, child["id"]) is None
        assert db.get(Conversation, seeded["conversation_id"]) is None
        assert db.get(Message, seeded["message_id"]) is None
