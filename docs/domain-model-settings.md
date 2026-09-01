# Domain model settings

Every domain and sub-domain can remember its own model and generation settings.
Open **Quick model tuning** at the top of Model Performance Optimizer, or open
the selected scope's **Settings** tab and expand **Domain model settings**. Make
the change and select **Save for this domain**. The choice is stored in local
PostgreSQL and is restored whenever that scope is selected. It does not alter
another domain, and no benchmark is required.

## The simple controls

- **Model** chooses one of the models already installed in Ollama.
- **Context window for each request** provides visible one-tap token choices.
  It is the total token budget shared by
  instructions, retrieved document excerpts, conversation history, the current
  question, and the answer.
- **Maximum answer length** provides Short, Standard, Long, and Very long
  buttons and reserves that part of the context for the response.
- **Response style** provides Precise, Balanced, and Creative presets. Precise
  is suitable for factual work and summaries, Balanced is the general default,
  and Creative permits more variation. A visible temperature slider allows a
  direct adjustment; Top P, Top K, and repeat penalty remain under **More
  response controls**.

**Use hardware-detected settings** appears when Ollama reports the context
allocation of the currently loaded model. If that evidence is unavailable, the
button is labelled **Use safe suggested settings** and retains the current
conservative context. Both choices also select Balanced sampling and reserve up
to 2,048 tokens for an answer. The advanced sampling sliders remain available
but are not required for normal use.

The suggestion is deliberately bounded by the model's reported native context.
A larger context can consume substantially more memory and may slow generation,
so a model advertising a large native maximum does not prove that the maximum
fits the current computer.

## Why two context numbers may appear

The left rail shows the selected domain's **request** limit. This is the value
the framework sends to Ollama as `num_ctx` for chat in that domain.

The performance panel can show **Ollama loaded allocation**. That is what
Ollama currently reports for a loaded model process. It is hardware/runtime
evidence, not the domain's saved request setting. For example, Ollama may have a
model loaded with 32K capacity while a domain intentionally sends 8K requests.
The labels stay separate so those values are not mistaken for each other.

Historical benchmark cards use **Profile context when measured** because they
describe a saved measurement, not necessarily the domain selected now.

## Preventing cut-off answers

Before generation, the framework reserves the selected maximum answer length.
If the assembled prompt is too large, it removes the oldest conversation turns
first while retaining the framework instructions and latest request. Ollama
also receives `num_predict`, so the intended answer limit is explicit.

If Ollama still finishes because that answer limit was reached, the response is
stored as **truncated** and the interface says that it reached the domain's
answer-length limit. The result no longer stops silently. The user can ask the
model to continue or increase the maximum answer length for that domain.

## Advanced sampling settings

- **Temperature** controls randomness. Lower is more repeatable; higher is more
  varied.
- **Top P** limits choices to a probability mass.
- **Top K** limits choices to a count of likely tokens.
- **Repeat penalty** discourages repeated phrases.

These values work together, which is why the three response-style presets are
the recommended interface. Hardware mainly determines practical model size,
context, answer capacity, and speed. Temperature and the other sampling values
change response behaviour; they do not make a larger context fit in memory.

The Model Performance Optimizer remains an optional advanced measurement tool.
Users do not need to run a benchmark to save safe per-domain settings.
