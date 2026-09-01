# Local Code Repository Search

This document records the current workflow, security boundary, implementation,
and verification.

## User workflow

1. Select the domain or sub-domain that should own the code.
2. Open the Documents tab and choose **Import repository snapshot (.zip)**.
3. Enter a display name and optional revision label, then confirm the exact
   scope, archive filename, and compressed size.
4. Review accepted, skipped, and security-excluded counts. Expand the
   exclusion list to see paths and safe reasons; excluded contents are never
   shown or indexed.
5. Ask a question in that same scope. Retrieved code is displayed separately
   in What the model sees and assistant citations identify repository, path,
   and inclusive line range.
6. Use **Replace / reindex** to upload a new immutable snapshot. The old one
   stays active until the replacement has fully validated and indexed. Use
   **Delete** and type the repository name to remove its grant, files, chunks,
   embeddings, related retrieval records, and stored snapshot.

## Security model

- Only user-uploaded ZIP snapshots are supported. There is no remote clone,
  live sync, arbitrary host path, Git command, shell, code execution, package
  installation, Docker socket, deployment, or model-controlled tool call.
- An import creates one backend-owned grant for one exact scope. Repository
  grants do not follow parent inheritance or sibling sharing, and allowed
  repository IDs are recalculated from the database on every retrieval.
- Archives are streamed to random private temporary names. Absolute, drive,
  traversal, NUL, duplicate normalized, encrypted, link, and special-entry
  paths fail the entire import. Default caps are 100 MiB compressed, 500 MiB
  expanded, 20,000 members, 2 MiB per searchable file, and a 100:1 member
  compression ratio; these are configurable through environment variables.
- Dependency, VCS, cache, generated, binary, archive, credential, key, and
  probable-secret files are excluded before their text is stored or embedded.
  Detection reduces risk but is not a guarantee, so users must still review
  the snapshot before importing it.
- Embeddings use the configured local Ollama embedding model. Search fuses
  deterministic exact path/symbol/content matching with local vector
  similarity, then caps results at eight excerpts and 12,000 characters.
- Repository content is wrapped as untrusted read-only source data below the
  framework security rules. Source comments, documentation, and filenames
  cannot override instructions or authorize actions. Retrieval failure adds
  no code and is explained in the inspector.

## Main implementation

- `backend/app/repository_pipeline.py`: archive validation, exclusions,
  secret screening, deterministic chunking, and local embeddings.
- `backend/app/repository_retrieval.py`: exact-scope grants and bounded hybrid
  retrieval.
- `backend/app/routers/repositories.py`: list/import/search/replace/delete
  lifecycle and recoverable storage cleanup.
- `backend/app/prompt_assembly.py`: separate repository layer, structured
  citations, and retrieval outcome logging.
- `frontend/components/RightRail.tsx`: import confirmation, status/exclusion
  review, replacement, and typed-name deletion.
- `frontend/components/ChatColumn.tsx`: repository/path/line citations.

## Verification

The complete backend suite passes 41/41 against real PostgreSQL/pgvector and
local Ollama. Repository-specific checks cover valid indexing and exact
symbol/path retrieval; parent, child, sibling, and unrelated-scope isolation;
traversal, absolute, NUL, drive, link, encrypted, expansion, member-count,
file-size, and compression-ratio rejection; dependency/generated/binary/
archive/credential/secret exclusions; no shell, process, code, or network use
during ingestion; untrusted prompt boundaries; citation provenance; empty
queries; result and prompt-character limits; embedding-outage fail-closed
behavior; atomic failed/successful replacement; retrieval-record cleanup; and
repository/scope deletion cascades.

The frontend production build also passes. Code repository search is therefore
shown as **Active/local** in Scope settings → Tools.
