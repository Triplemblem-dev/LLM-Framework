"""Shared request helpers for the isolation tests. Plain functions
(not fixtures) so tests can call them directly with whatever client/domain
they already have in scope.
"""

import json
import io
import uuid
import zipfile


def uniq(base: str) -> str:
    """A short random suffix keeps every test run's domain names distinct,
    so slug collisions and stale data from a previous failed run never
    interfere with a fresh run."""
    return f"{base} [test-{uuid.uuid4().hex[:8]}]"


def upload_doc(client, domain_id: str, filename: str, text: str) -> dict:
    resp = client.post(
        f"/domains/{domain_id}/documents",
        files={"file": (filename, text.encode("utf-8"), "text/markdown")},
    )
    resp.raise_for_status()
    return resp.json()


def repository_zip(entries: dict[str, str | bytes]) -> bytes:
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries.items():
            archive.writestr(path, content.encode("utf-8") if isinstance(content, str) else content)
    return archive_bytes.getvalue()


def upload_repository(
    client,
    domain_id: str,
    entries: dict[str, str | bytes],
    *,
    filename: str = "repository.zip",
    name: str = "Test repository",
    revision_label: str = "test-snapshot",
) -> dict:
    resp = client.post(
        f"/domains/{domain_id}/repositories",
        files={"file": (filename, repository_zip(entries), "application/zip")},
        data={"name": name, "revision_label": revision_label},
    )
    resp.raise_for_status()
    return resp.json()


def preview(client, domain_id: str, draft: str, conversation_id: str | None = None) -> dict[str, dict]:
    """Returns the assembled prompt layers keyed by layer name, e.g.
    layers["10. Retrieved local documents"]["content"]."""
    params = {"draft": draft}
    if conversation_id:
        params["conversation_id"] = conversation_id
    resp = client.get(f"/domains/{domain_id}/prompt-preview", params=params)
    resp.raise_for_status()
    return {layer["name"]: layer for layer in resp.json()["layers"]}


def send_chat(client, domain_id: str, text: str, conversation_id: str | None = None) -> dict:
    """Sends a real chat message and consumes the NDJSON stream to
    completion. Returns {"text", "citations", "conversation_id", "message_id"}."""
    payload: dict = {"text": text}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    full_text = ""
    citations: list[dict] = []
    conv_id = None
    message_id = None
    metrics = None

    with client.stream("POST", f"/domains/{domain_id}/messages", json=payload) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            event = json.loads(line)
            if event["type"] == "token":
                full_text += event["text"]
            elif event["type"] == "error":
                raise RuntimeError(f"chat stream error: {event['detail']}")
            elif event["type"] == "done":
                citations = event["citations"]
                conv_id = event["conversation_id"]
                message_id = event["message_id"]
                metrics = event.get("metrics")

    return {
        "text": full_text,
        "citations": citations,
        "conversation_id": conv_id,
        "message_id": message_id,
        "metrics": metrics,
    }
