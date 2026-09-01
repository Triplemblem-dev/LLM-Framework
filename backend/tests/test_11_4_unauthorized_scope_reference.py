"""Unauthorized scope-reference tests.

The model must never construct database filters, decide its own access list,
or authorize scope references.
These tests act like a client that (accidentally or otherwise) references
a resource ID that belongs to a different scope than the one it's calling
through, and check the backend rejects or safely ignores it rather than
mixing data across the boundary.
"""

import uuid

from tests.helpers import send_chat, uniq


def test_message_with_foreign_conversation_id_is_rejected(client, domain_factory):
    alpha = domain_factory(uniq("Alpha"))
    beta = domain_factory(uniq("Beta"))

    alpha_result = send_chat(client, alpha["id"], "hello from alpha")
    foreign_conversation_id = alpha_result["conversation_id"]

    resp = client.post(
        f"/domains/{beta['id']}/messages",
        json={"text": "hello from beta", "conversation_id": foreign_conversation_id},
    )

    assert resp.status_code == 404


def test_prompt_preview_ignores_foreign_conversation_history(client, domain_factory):
    alpha = domain_factory(uniq("Alpha"))
    beta = domain_factory(uniq("Beta"))

    alpha_result = send_chat(client, alpha["id"], "the secret alpha phrase is PINEAPPLE-CODE")
    foreign_conversation_id = alpha_result["conversation_id"]

    resp = client.get(
        f"/domains/{beta['id']}/prompt-preview",
        params={"draft": "what did we talk about?", "conversation_id": foreign_conversation_id},
    )
    resp.raise_for_status()
    layers = {layer["name"]: layer for layer in resp.json()["layers"]}

    history_layer = layers["12. Recent conversation messages"]
    assert history_layer["applied"] is False
    assert "PINEAPPLE-CODE" not in history_layer["content"]


def test_delete_document_through_wrong_scope_is_rejected(client, domain_factory):
    alpha = domain_factory(uniq("Alpha"))
    beta = domain_factory(uniq("Beta"))

    upload_resp = client.post(
        f"/domains/{alpha['id']}/documents",
        files={"file": ("alpha.md", b"# Doc\ncontent", "text/markdown")},
    )
    upload_resp.raise_for_status()
    document_id = upload_resp.json()["id"]

    resp = client.delete(f"/domains/{beta['id']}/documents/{document_id}")
    assert resp.status_code == 404

    still_there = client.get(f"/domains/{alpha['id']}/documents")
    still_there.raise_for_status()
    assert any(d["id"] == document_id for d in still_there.json())


def test_unknown_domain_id_is_rejected_everywhere(client):
    random_id = str(uuid.uuid4())

    assert client.get(f"/domains/{random_id}/documents").status_code == 404
    assert client.get(f"/domains/{random_id}/documents/inherited").status_code == 404
    assert client.get(f"/domains/{random_id}/conversations").status_code == 404
    assert client.get(f"/domains/{random_id}/prompt-preview", params={"draft": "hi"}).status_code == 404
    assert client.post(f"/domains/{random_id}/messages", json={"text": "hi"}).status_code == 404
    assert client.post(f"/domains/{random_id}/subdomains", json={"name": "x"}).status_code == 404
