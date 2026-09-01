"""Per-scope local-owner controls for the real prompt assembler."""

import uuid

from app.db import SessionLocal
from app.models import Domain, Message, MessageRole
from app.prompt_assembly import OWNER_CONTROLLED_LAYER_KEYS, assemble
from tests.helpers import preview, uniq


def _set_layer(client, domain_id: str, key: str, enabled: bool, *, acknowledge: bool = False):
    return client.put(
        f"/domains/{domain_id}/prompt-layers/{key}",
        json={"enabled": enabled, "risk_acknowledged": acknowledge},
    )


def test_default_metadata_exposes_all_real_owner_controls(client, domain_factory):
    domain = domain_factory(uniq("Layer controls"), prompt="LOCAL-SCOPE-PROMPT")
    layers = preview(client, domain["id"], "question")
    by_key = {layer["key"]: layer for layer in layers.values()}

    assert {key for key, layer in by_key.items() if layer["control"] in {"standard", "advanced"}} == set(
        OWNER_CONTROLLED_LAYER_KEYS
    )
    assert all(by_key[key]["owner_enabled"] is True for key in OWNER_CONTROLLED_LAYER_KEYS)
    assert by_key["framework_security"]["control"] == "advanced"
    assert by_key["model_instructions"]["control"] == "advanced"
    assert by_key["current_user_message"]["control"] == "fixed"
    assert by_key["user_preferences"]["control"] == "planned"


def test_standard_control_is_persistent_per_scope_and_reversible(client, domain_factory):
    first = domain_factory(uniq("First"), prompt="FIRST-SCOPE-MARKER")
    second = domain_factory(uniq("Second"), prompt="SECOND-SCOPE-MARKER")

    response = _set_layer(client, first["id"], "current_scope", False)
    response.raise_for_status()
    assert response.json() == {"key": "current_scope", "enabled": False}

    first_layer = preview(client, first["id"], "question")["6. Sub-domain / domain prompt"]
    second_layer = preview(client, second["id"], "question")["6. Sub-domain / domain prompt"]
    assert first_layer["owner_enabled"] is False
    assert first_layer["state"] == "not_included"
    assert "Disabled by the owner" in first_layer["reason"]
    assert second_layer["owner_enabled"] is True
    assert second_layer["state"] == "included"

    _set_layer(client, first["id"], "current_scope", True).raise_for_status()
    restored = preview(client, first["id"], "question")["6. Sub-domain / domain prompt"]
    assert restored["owner_enabled"] is True
    assert restored["state"] == "included"

    with SessionLocal() as db:
        scope = db.get(Domain, uuid.UUID(first["id"]))
        assert "current_scope" not in scope.prompt_layer_overrides


def test_advanced_controls_require_acknowledgement_and_fixed_keys_are_rejected(client, domain_factory):
    domain = domain_factory(uniq("Advanced controls"), prompt="scope")

    refused = _set_layer(client, domain["id"], "framework_security", False)
    assert refused.status_code == 400
    assert "acknowledgement" in refused.json()["detail"].lower()
    assert preview(client, domain["id"], "question")["1. Framework security rules"]["owner_enabled"] is True

    accepted = _set_layer(client, domain["id"], "framework_security", False, acknowledge=True)
    accepted.raise_for_status()
    security = preview(client, domain["id"], "question")["1. Framework security rules"]
    assert security["owner_enabled"] is False
    assert security["state"] == "not_included"

    assert _set_layer(client, domain["id"], "current_user_message", False).status_code == 400
    assert _set_layer(client, domain["id"], "user_preferences", False).status_code == 400
    assert _set_layer(client, domain["id"], "unknown_layer", False).status_code == 400

    _set_layer(client, domain["id"], "framework_security", True).raise_for_status()


def test_controls_change_real_role_payload_without_deleting_history(client, domain_factory):
    domain = domain_factory(uniq("Payload controls"), prompt="SCOPE-PROMPT-MARKER")
    for key in ("framework_security", "model_instructions"):
        _set_layer(client, domain["id"], key, False, acknowledge=True).raise_for_status()
    _set_layer(client, domain["id"], "current_scope", False).raise_for_status()
    _set_layer(client, domain["id"], "conversation_history", False).raise_for_status()

    stored_history = [
        Message(role=MessageRole.user, content="STORED-USER-HISTORY"),
        Message(role=MessageRole.assistant, content="STORED-ASSISTANT-HISTORY"),
    ]
    with SessionLocal() as db:
        scope = db.get(Domain, uuid.UUID(domain["id"]))
        result = assemble(db, scope, stored_history, "CURRENT-REQUEST")

    assert result.messages == [{"role": "user", "content": "CURRENT-REQUEST"}]
    assert stored_history[0].content == "STORED-USER-HISTORY"
    by_key = {layer["key"]: layer for layer in result.layers}
    assert by_key["framework_security"]["state"] == "not_included"
    assert by_key["model_instructions"]["state"] == "not_included"
    assert by_key["current_scope"]["state"] == "not_included"
    assert by_key["conversation_history"]["state"] == "not_included"
    assert by_key["current_user_message"]["state"] == "included"


def test_disabled_retrieval_layers_contribute_no_sources_or_citations(client, domain_factory):
    domain = domain_factory(uniq("Retrieval controls"), prompt="scope")
    for key in ("shared_documents", "local_documents", "code_repositories"):
        _set_layer(client, domain["id"], key, False).raise_for_status()

    with SessionLocal() as db:
        scope = db.get(Domain, uuid.UUID(domain["id"]))
        result = assemble(db, scope, [], "search for private source material")

    assert result.citations == []
    assert result.retrieved_chunk_ids == []
    assert result.retrieved_code_chunk_ids == []
    assert result.code_repository_ids == []
    assert result.code_retrieval_outcome == "disabled_by_owner"
    by_key = {layer["key"]: layer for layer in result.layers}
    for key in ("shared_documents", "local_documents", "code_repositories"):
        assert by_key[key]["owner_enabled"] is False
        assert by_key[key]["state"] == "not_included"
