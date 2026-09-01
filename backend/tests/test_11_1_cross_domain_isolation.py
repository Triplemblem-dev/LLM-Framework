"""Cross-domain and sibling-leakage tests.

Uses secret markers against disposable per-test domains rather than the user's
real data.
"""

from tests.helpers import preview, uniq, upload_doc


def test_unrelated_top_level_domains_never_cross_contaminate(client, domain_factory):
    alpha = domain_factory(uniq("Alpha"))
    beta = domain_factory(uniq("Beta"))

    upload_doc(client, alpha["id"], "alpha.md", "# Secret Marker\nThe marker is ALPHA-11111.")
    upload_doc(client, beta["id"], "beta.md", "# Secret Marker\nThe marker is BETA-22222.")

    alpha_layers = preview(client, alpha["id"], "what is the secret marker?")
    beta_layers = preview(client, beta["id"], "what is the secret marker?")

    assert "ALPHA-11111" in alpha_layers["10. Retrieved local documents"]["content"]
    assert "BETA-22222" not in alpha_layers["10. Retrieved local documents"]["content"]
    assert alpha_layers["9. Retrieved shared documents"]["applied"] is False

    assert "BETA-22222" in beta_layers["10. Retrieved local documents"]["content"]
    assert "ALPHA-11111" not in beta_layers["10. Retrieved local documents"]["content"]
    assert beta_layers["9. Retrieved shared documents"]["applied"] is False


def test_private_subdomain_sees_neither_parent_nor_sibling(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    private_child = domain_factory(uniq("PrivateChild"), parent_id=parent["id"])
    inherited_sibling = domain_factory(uniq("InheritedSibling"), parent_id=parent["id"])

    client.patch(f"/domains/{private_child['id']}", json={"inheritance": "private"}).raise_for_status()

    upload_doc(client, parent["id"], "parent.md", "# Secret Marker\nThe marker is PARENT-33333.")
    upload_doc(client, inherited_sibling["id"], "sibling.md", "# Secret Marker\nThe marker is SIBLING-44444.")

    layers = preview(client, private_child["id"], "what is the secret marker?")

    assert layers["9. Retrieved shared documents"]["applied"] is False
    assert "PARENT-33333" not in layers["9. Retrieved shared documents"]["content"]
    assert "SIBLING-44444" not in layers["9. Retrieved shared documents"]["content"]
    assert layers["10. Retrieved local documents"]["applied"] is False


def test_sibling_isolation_is_default(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    sib_a = domain_factory(uniq("SibA"), parent_id=parent["id"])
    sib_b = domain_factory(uniq("SibB"), parent_id=parent["id"])

    upload_doc(client, sib_a["id"], "a.md", "# Secret Marker\nThe marker is SIBA-55555.")
    upload_doc(client, sib_b["id"], "b.md", "# Secret Marker\nThe marker is SIBB-66666.")

    layers_a = preview(client, sib_a["id"], "what is the secret marker?")
    layers_b = preview(client, sib_b["id"], "what is the secret marker?")

    assert "SIBB-66666" not in layers_a["9. Retrieved shared documents"]["content"]
    assert "SIBB-66666" not in layers_a["10. Retrieved local documents"]["content"]
    assert "SIBA-55555" not in layers_b["9. Retrieved shared documents"]["content"]
    assert "SIBA-55555" not in layers_b["10. Retrieved local documents"]["content"]
