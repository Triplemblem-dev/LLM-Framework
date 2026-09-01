"""Manual-memory scope, inheritance, source, editing, and deletion tests.

Mirrors the document tests in structure: memories follow the
exact same approved_scope_ids() inheritance/sharing rules as documents and
prompts, so the isolation assertions here are deliberately the same shape
as the related document and prompt tests, proving the new resource type did not get its own,
possibly-inconsistent access-control path.
"""

from tests.helpers import preview, send_chat, uniq


def test_create_list_update_delete_memory(client, domain_factory):
    domain = domain_factory(uniq("Notes"))

    create_resp = client.post(f"/domains/{domain['id']}/memories", json={"content": "Always answer in Dutch."})
    create_resp.raise_for_status()
    memory = create_resp.json()
    assert memory["content"] == "Always answer in Dutch."
    assert memory["conversation_id"] is None

    listed = client.get(f"/domains/{domain['id']}/memories")
    listed.raise_for_status()
    assert [m["id"] for m in listed.json()] == [memory["id"]]

    update_resp = client.patch(f"/domains/{domain['id']}/memories/{memory['id']}", json={"content": "Always answer in French."})
    update_resp.raise_for_status()
    assert update_resp.json()["content"] == "Always answer in French."

    delete_resp = client.delete(f"/domains/{domain['id']}/memories/{memory['id']}")
    assert delete_resp.status_code == 200

    listed_after = client.get(f"/domains/{domain['id']}/memories")
    listed_after.raise_for_status()
    assert listed_after.json() == []


def test_empty_memory_content_is_rejected(client, domain_factory):
    domain = domain_factory(uniq("Notes"))
    resp = client.post(f"/domains/{domain['id']}/memories", json={"content": "   "})
    assert resp.status_code == 400


def test_memory_saved_from_chat_is_traceable_to_its_conversation(client, domain_factory):
    domain = domain_factory(uniq("Notes"))
    result = send_chat(client, domain["id"], "hello")
    conversation_id = result["conversation_id"]

    resp = client.post(
        f"/domains/{domain['id']}/memories",
        json={"content": "The user prefers concise answers.", "conversation_id": conversation_id},
    )
    resp.raise_for_status()
    assert resp.json()["conversation_id"] == conversation_id


def test_memory_with_foreign_conversation_id_is_dropped_not_leaked(client, domain_factory):
    """Same unauthorized-scope-reference posture as prompt-preview: a
    conversation_id belonging to a different domain is silently dropped rather
    than erroring or being trusted."""
    alpha = domain_factory(uniq("Alpha"))
    beta = domain_factory(uniq("Beta"))

    alpha_result = send_chat(client, alpha["id"], "hello from alpha")
    foreign_conversation_id = alpha_result["conversation_id"]

    resp = client.post(
        f"/domains/{beta['id']}/memories",
        json={"content": "note", "conversation_id": foreign_conversation_id},
    )
    resp.raise_for_status()
    assert resp.json()["conversation_id"] is None


def test_update_and_delete_through_wrong_scope_are_rejected(client, domain_factory):
    alpha = domain_factory(uniq("Alpha"))
    beta = domain_factory(uniq("Beta"))

    create_resp = client.post(f"/domains/{alpha['id']}/memories", json={"content": "alpha-only note"})
    create_resp.raise_for_status()
    memory_id = create_resp.json()["id"]

    assert client.patch(f"/domains/{beta['id']}/memories/{memory_id}", json={"content": "hijacked"}).status_code == 404
    assert client.delete(f"/domains/{beta['id']}/memories/{memory_id}").status_code == 404

    still_there = client.get(f"/domains/{alpha['id']}/memories")
    still_there.raise_for_status()
    assert still_there.json()[0]["content"] == "alpha-only note"


def test_unrelated_top_level_domains_never_share_memories(client, domain_factory):
    alpha = domain_factory(uniq("Alpha"))
    beta = domain_factory(uniq("Beta"))

    client.post(f"/domains/{alpha['id']}/memories", json={"content": "ALPHAMEM-11111"}).raise_for_status()
    client.post(f"/domains/{beta['id']}/memories", json={"content": "BETAMEM-22222"}).raise_for_status()

    alpha_layers = preview(client, alpha["id"], "")
    beta_layers = preview(client, beta["id"], "")

    assert "ALPHAMEM-11111" in alpha_layers["8. Local memories"]["content"]
    assert "BETAMEM-22222" not in alpha_layers["8. Local memories"]["content"]
    assert alpha_layers["7. Approved inherited memories"]["applied"] is False

    assert "BETAMEM-22222" in beta_layers["8. Local memories"]["content"]
    assert "ALPHAMEM-11111" not in beta_layers["8. Local memories"]["content"]


def test_inherited_subdomain_sees_parent_memory(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    child = domain_factory(uniq("Child"), parent_id=parent["id"])  # defaults to inherited

    client.post(f"/domains/{parent['id']}/memories", json={"content": "PARENTMEM-33333"}).raise_for_status()

    layers = preview(client, child["id"], "")
    assert layers["7. Approved inherited memories"]["applied"] is True
    assert "PARENTMEM-33333" in layers["7. Approved inherited memories"]["content"]


def test_private_subdomain_does_not_inherit_parent_memory(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    child = domain_factory(uniq("Child"), parent_id=parent["id"])
    client.patch(f"/domains/{child['id']}", json={"inheritance": "private"}).raise_for_status()

    client.post(f"/domains/{parent['id']}/memories", json={"content": "PARENTMEM-44444"}).raise_for_status()

    layers = preview(client, child["id"], "")
    assert layers["7. Approved inherited memories"]["applied"] is False
    assert "PARENTMEM-44444" not in layers["7. Approved inherited memories"]["content"]


def test_share_with_siblings_applies_to_memories_too(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    source = domain_factory(uniq("Source"), parent_id=parent["id"])
    sibling = domain_factory(uniq("Sibling"), parent_id=parent["id"])

    client.post(f"/domains/{source['id']}/memories", json={"content": "SHAREMEM-55555"}).raise_for_status()

    before = preview(client, sibling["id"], "")
    assert "SHAREMEM-55555" not in before["7. Approved inherited memories"]["content"]

    client.patch(f"/domains/{source['id']}", json={"share_with_siblings": True}).raise_for_status()
    during = preview(client, sibling["id"], "")
    assert "SHAREMEM-55555" in during["7. Approved inherited memories"]["content"]


def test_inherited_memories_endpoint_matches_prompt_layer(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    child = domain_factory(uniq("Child"), parent_id=parent["id"])

    client.post(f"/domains/{parent['id']}/memories", json={"content": "ENDPOINTMEM-66666"}).raise_for_status()

    resp = client.get(f"/domains/{child['id']}/memories/inherited")
    resp.raise_for_status()
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["content"] == "ENDPOINTMEM-66666"
    assert rows[0]["scope_name"] == parent["name"]
