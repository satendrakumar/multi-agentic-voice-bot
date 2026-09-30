# Prompts

All prompt text for the bot lives here, in one folder per version. The code (`sania/`) keeps only the
contracts: the JSON schema each agent returns, routing, and the compliance guard.

```
prompts/
  v1/
    shared.md                 rules added to every agent's system prompt
    identity.md               Agent 1: greeting & identity verification
    disclosure.md             Agent 2: account disclosure
    reason.md                 Agent 3: reason discovery
    negotiation.md            Agent 4: negotiation (reacts to the caller, phrases the move)
    negotiation_moves.toml    instruction text for each negotiation move chosen by code
    dispute.md                Agent 5: dispute & levers
    servicing.md              Agent 6: special cases
    safety.md                 Agent 7: hard-stop responder
    classifier.md             Agent 7: hard-stop classifier
    closing.md                Agent 8: closing
    transliterate.md          customer name -> Devanagari
```

## Using a version

Set `SANIA_PROMPT_VERSION` in `.env` (default `v1`). The files are read once per process.

## Making a new version

1. Copy the current folder: `cp -r prompts/v1 prompts/v2`.
2. Edit the files in `v2`, and add a line to the changelog below.
3. Try it: `SANIA_PROMPT_VERSION=v2 uv run python main.py`.
4. When it is better, set `SANIA_PROMPT_VERSION=v2` in `.env`.

Keep old versions for comparison. `uv run pytest` checks that every version has the full set of files.

## Rules for prompt authors

- **Placeholders:** examples may write the customer's name as `<name>`; the guard replaces it with the real name. In `negotiation_moves.toml`, `{mad}` is the minimum amount in words and `{line}` is the angle text.
- **JSON fields:** the fields a prompt asks for must exist in the agent's `signals_schema` in `sania/agents/*.py`. Adding a field means changing the code too.
- **Enforced rules:** rules the guard enforces (`sania/guard.py`) can be restated in the prompt, but the guard stays the final check.

## Changelog

| Version | Date | Changes |
|---|---|---|
| v1 | 2026-09-30 | First versioned set. Short rules plus worked examples for small local models (Qwen3.5-4B). Negotiation strategy is chosen in code (`next_move`); the prompt only phrases the move. |
