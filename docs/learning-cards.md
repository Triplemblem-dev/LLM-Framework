# Learning cards

**Learning cards** is an optional tool for the
latest completed assistant response in the active conversation. It does not
change or replace the original response.

Selecting **Make learning cards** directly beneath the latest assistant
response asks the active local Ollama model to create:

- one short summary sentence;
- exactly four cards; and
- one short title and one concrete takeaway per card.

Cards are deliberately plain and compact. They contain no hidden explanation,
quiz, score, or spaced-repetition system. A small category label distinguishes
a key idea, action, caution, or source-provided example.

## Behavior and storage

- The backend chooses the latest message and requires it to be a completed
  assistant response. The client cannot nominate an older or arbitrary message.
- A newer message arriving while cards are generated makes the request stale;
  the result is rejected rather than attached to the wrong response.
- The original response remains visible and unchanged.
- Generated cards are stored on their source message in PostgreSQL, survive a
  reload, and are deleted with that message or conversation.
- **Refresh cards** replaces only the saved card deck for the same latest
  response.
- Older two- or three-card decks remain readable. Refreshing one replaces it
  with a new four-card deck.

## Model boundary

Only the selected assistant response is sent to the compaction request. Its
text is structurally marked as untrusted data, not instructions. The model is
required to use only facts present in the response, preserve qualifications,
and return a bounded JSON structure. Invalid structured output produces a
visible error and is not saved.

The visual treatment uses a restrained card grid, clear type hierarchy,
muted metadata, category pills, and one accent color. These are general design
principles informed by research into shipped card and progressive-disclosure
interfaces; no third-party screen is copied.
