"""Prompt-inspector Slice 2: authoritative layer metadata.

These checks deliberately exercise the real prompt-preview endpoint. They do
not duplicate prompt assembly in the test client; the response must explain
the same layers that chat generation receives.
"""

from tests.helpers import preview, uniq


REQUIRED_FIELDS = {
    "key",
    "name",
    "category",
    "content",
    "applied",
    "state",
    "reason",
    "source_type",
    "source_name",
    "edit_target",
    "model_role",
    "control",
    "owner_enabled",
}


def test_preview_layers_have_stable_explanation_metadata(client, domain_factory):
    domain = domain_factory(uniq("Inspector"), prompt="Only answer questions about this test scope.")
    response = client.get(f"/domains/{domain['id']}/prompt-preview", params={"draft": "Explain this scope"})
    response.raise_for_status()
    layers = response.json()["layers"]

    assert len(layers) == 14
    assert len({layer["key"] for layer in layers}) == len(layers)
    assert all(REQUIRED_FIELDS == set(layer) for layer in layers)
    assert [layer["category"] for layer in layers] == (
        ["rules"] * 3 + ["scope"] * 3 + ["knowledge"] * 5 + ["conversation"] * 3
    )

    by_key = {layer["key"]: layer for layer in layers}
    assert by_key["framework_security"]["state"] == "included"
    assert by_key["framework_security"]["model_role"] == "system"
    assert by_key["framework_security"]["control"] == "advanced"
    assert by_key["framework_security"]["owner_enabled"] is True
    assert by_key["user_preferences"]["state"] == "planned"
    assert by_key["user_preferences"]["model_role"] is None
    assert by_key["user_preferences"]["control"] == "planned"
    assert by_key["user_preferences"]["owner_enabled"] is None
    assert by_key["current_scope"]["edit_target"] == "scope_settings"
    assert by_key["code_repositories"]["edit_target"] == "repositories"
    assert "no ready repository snapshot" in by_key["code_repositories"]["reason"]
    assert by_key["current_user_message"]["state"] == "included"
    assert by_key["current_user_message"]["model_role"] == "user"
    assert by_key["current_user_message"]["control"] == "fixed"
    assert by_key["current_user_message"]["owner_enabled"] is None


def test_parent_reason_distinguishes_top_level_private_and_missing_prompt(client, domain_factory):
    parent = domain_factory(uniq("Parent"), prompt="")
    child = domain_factory(uniq("Child"), parent_id=parent["id"])

    parent_layers = preview(client, parent["id"], "")
    assert "top-level domain has no parent" in parent_layers["4. Parent-domain prompt"]["reason"]
    assert parent_layers["4. Parent-domain prompt"]["edit_target"] is None

    child_layers = preview(client, child["id"], "")
    assert "has no scope prompt" in child_layers["4. Parent-domain prompt"]["reason"]
    assert child_layers["4. Parent-domain prompt"]["source_name"] == parent["name"]
    assert child_layers["4. Parent-domain prompt"]["edit_target"] == "parent_scope"

    client.patch(f"/domains/{child['id']}", json={"inheritance": "private"}).raise_for_status()
    private_layers = preview(client, child["id"], "")
    assert "private from its parent" in private_layers["4. Parent-domain prompt"]["reason"]


def test_document_reason_distinguishes_empty_draft_permission_and_availability(client, domain_factory):
    domain = domain_factory(uniq("Documents"))

    empty_layers = preview(client, domain["id"], "")
    assert "waits for a non-empty draft" in empty_layers["10. Retrieved local documents"]["reason"]

    draft_layers = preview(client, domain["id"], "find a document")
    assert "no searchable document passages" in draft_layers["10. Retrieved local documents"]["reason"]
    assert "no approved parent or sibling scopes" in draft_layers["9. Retrieved shared documents"]["reason"]


def test_conversation_and_user_layers_identify_distinct_model_roles(client, domain_factory):
    domain = domain_factory(uniq("Roles"))
    layers = preview(client, domain["id"], "new question")

    assert layers["12. Recent conversation messages"]["model_role"] == "conversation"
    assert layers["12. Recent conversation messages"]["state"] == "not_included"
    assert layers["13. Current user message"]["model_role"] == "user"
    assert layers["13. Current user message"]["content"] == "new question"
