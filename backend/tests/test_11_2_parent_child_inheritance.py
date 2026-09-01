"""Parent-child inheritance tests."""

from tests.helpers import preview, uniq, upload_doc


def test_inherited_subdomain_sees_parent_document(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    child = domain_factory(uniq("Child"), parent_id=parent["id"])  # defaults to inherited

    upload_doc(client, parent["id"], "parent.md", "# Secret Marker\nThe marker is PARENT-77777.")

    layers = preview(client, child["id"], "what is the secret marker?")

    assert layers["9. Retrieved shared documents"]["applied"] is True
    assert "PARENT-77777" in layers["9. Retrieved shared documents"]["content"]


def test_private_subdomain_does_not_inherit_parent_document(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    child = domain_factory(uniq("Child"), parent_id=parent["id"])
    client.patch(f"/domains/{child['id']}", json={"inheritance": "private"}).raise_for_status()

    upload_doc(client, parent["id"], "parent.md", "# Secret Marker\nThe marker is PARENT-88888.")

    layers = preview(client, child["id"], "what is the secret marker?")

    assert layers["9. Retrieved shared documents"]["applied"] is False
    assert "PARENT-88888" not in layers["9. Retrieved shared documents"]["content"]


def test_local_document_narrows_without_losing_parent_context(client, domain_factory):
    """A child should see both its own local document AND the inherited parent
    document at once - narrowing adds context, it does not replace it."""
    parent = domain_factory(uniq("Parent"))
    child = domain_factory(uniq("Child"), parent_id=parent["id"])

    upload_doc(client, parent["id"], "parent.md", "# Secret Marker\nThe marker is PARENT-99999.")
    upload_doc(client, child["id"], "child.md", "# Secret Marker\nThe marker is CHILD-10101.")

    layers = preview(client, child["id"], "what is the secret marker?")

    assert "PARENT-99999" in layers["9. Retrieved shared documents"]["content"]
    assert "CHILD-10101" in layers["10. Retrieved local documents"]["content"]


def test_share_with_siblings_toggle_takes_effect_immediately(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    source = domain_factory(uniq("Source"), parent_id=parent["id"])
    sibling = domain_factory(uniq("Sibling"), parent_id=parent["id"])

    upload_doc(client, source["id"], "source.md", "# Secret Marker\nThe marker is SHARE-20202.")

    before = preview(client, sibling["id"], "what is the secret marker?")
    assert "SHARE-20202" not in before["9. Retrieved shared documents"]["content"]

    client.patch(f"/domains/{source['id']}", json={"share_with_siblings": True}).raise_for_status()
    during = preview(client, sibling["id"], "what is the secret marker?")
    assert "SHARE-20202" in during["9. Retrieved shared documents"]["content"]

    client.patch(f"/domains/{source['id']}", json={"share_with_siblings": False}).raise_for_status()
    after = preview(client, sibling["id"], "what is the secret marker?")
    assert "SHARE-20202" not in after["9. Retrieved shared documents"]["content"]


def test_two_level_nesting_is_rejected(client, domain_factory):
    parent = domain_factory(uniq("Parent"))
    child = domain_factory(uniq("Child"), parent_id=parent["id"])

    resp = client.post(f"/domains/{child['id']}/subdomains", json={"name": uniq("Grandchild"), "prompt": ""})

    assert resp.status_code == 400
