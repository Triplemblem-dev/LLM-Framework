# AI Document Organizer

The Documents panel can use an installed local Ollama model to propose a
consistent virtual folder structure and tags for the documents in one domain
or sub-domain.

## Workflow

1. Upload and index the documents in the intended scope.
2. Expand **AI document organizer** in the Documents panel.
3. Keep **Recommended automatically** or select a specific installed model.
4. Select **Generate organization preview**.
5. Review and edit the virtual folder and comma-separated tags for every file.
6. Confirm that the complete preview was reviewed and select **Apply
   organization**.

The automatic recommendation chooses the largest installed Ollama model that
does not look like an embedding model. This is a transparent size-based
heuristic, not a claim that model quality has been benchmarked. Selecting a
specific installed model overrides the recommendation.

## What changes

Folders and tags are metadata stored with each document. Applying a preview
does not move, copy, rename, or rewrite the original files. The Documents panel
groups files by their virtual folder, and retrieved source excerpts include
the folder and tags so the chat model can understand the organization.

Vector similarity remains the primary retrieval mechanism. Folders improve
human navigation and provide useful source metadata; they are not a substitute
for embeddings and do not make a promise that every query will run faster.

## Review and safety boundaries

- Organization is limited to the current domain or sub-domain. Inherited
  documents are read-only and excluded from the preview.
- Only filenames, existing organization metadata, and short indexed excerpts
  are sent to the selected local Ollama model.
- Filenames and excerpts are marked as untrusted data in the organizer prompt.
- The model must return every current document exactly once. Unknown,
  duplicate, missing, malformed, or excessive folder/tag values are rejected.
- A preview is bound to a hash of the current document set. Uploading,
  deleting, or replacing documents makes the preview stale and apply returns a
  conflict instead of silently using it.
- Users can edit all suggestions, and apply requires an explicit review
  acknowledgement.

## Current limits

One preview supports up to 50 local documents in a scope. A document without
indexed text can still be organized from its filename, and the preview shows a
warning. Model suggestions can be imperfect, so folders and tags should be
treated as recommendations rather than authoritative classifications.
