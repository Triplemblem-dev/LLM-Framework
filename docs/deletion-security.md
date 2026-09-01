# Secure deletion semantics

These deletion rules apply to domains, sub-domains, and conversations.

## Security boundary

Deletion targets are resolved and ownership-checked by the backend. The browser supplies an ID,
but that ID is never treated as proof of access. Missing, foreign-scope, and foreign-owner targets
return `404` without revealing whether another owner has a matching object.

The UI provides accident prevention, not authorization: it shows a consequence-specific modal,
requires the exact scope name before deleting a domain or sub-domain, and disables deletion while
a response is streaming. API authorization and ownership checks remain authoritative.

## Conversation deletion

`DELETE /domains/{scope_id}/conversations/{conversation_id}` requires the conversation to belong
to both the authenticated owner and the scope in the URL. PostgreSQL cascades deletion to messages
and retrieval logs. Citations are stored on messages and therefore disappear with them.

A manually saved memory is an independent scope resource, not a child of its source conversation.
It survives conversation deletion and its nullable `conversation_id` becomes `NULL`, preserving the
rule that deliberately saved memory outlives ephemeral chat history.

## Domain and sub-domain deletion

`DELETE /domains/{scope_id}` walks the complete descendant tree and verifies that every descendant
has the same owner before deleting anything. The database foreign keys then cascade through child
scopes, conversations, messages, documents and chunks, memories, scope-access logs, and retrieval
logs in one transaction.

Document bytes live outside PostgreSQL. Before committing the database deletion, each affected
scope directory is atomically moved into a private `.deleting` directory under the configured
document-storage root. Unsafe paths and symlinks are rejected. If the database transaction fails,
the directories are restored. After commit, the staged directories are physically removed. A
cleanup failure is logged and returned to the client as `storage_cleanup_complete=false` instead
of being silently reported as complete.

## Recovery limitation

Deletion is permanent and has no in-app undo. Recovery requires a backup created before deletion.
Archive remains the intended future non-destructive alternative but is not implemented yet.
