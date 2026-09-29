# S1 — Language & Style Manager (deterministic)

| | |
|---|---|
| **Kind** | Code (+ one optional LLM/transliteration call at call start) |
| **Runs** | Call start (transliteration), every caller turn (language tracking), every bot turn (tag) |

## 1. Responsibilities
1. **Name transliteration** — once at call start: `{NAME}` → Devanagari `[NAME]` (e.g. Rahul → राहुल). It is used in every mode, English included. `{NAME}` is never spoken raw.
2. **Language mirroring (bot turns 1–3)** — reply in the language the caller **mostly** speaks (the dominant script wins).
3. **Language lock (from bot turn 4)** — lock the turn-3 language for the whole call.
4. **Explicit switch** — "in English" / "English में बोलो" / "हिंदी में बोलो" → a new lock, immediately.
5. **Noise immunity** — a stray word, a one-word acknowledgement ("ok", "हाँ", "yes") or STT noise **never** flips the language.
6. **Tag** — prepend `<|HINDI|>` or `<|ENGLISH|>`. Nothing may come before the tag. Voicemail is always `<|ENGLISH|>`.

## 2. Algorithms

### 2.1 Transliteration
```python
def transliterate_name(name: str) -> str:
    # 1. lookup table of common Indian names (fast, deterministic)
    # 2. fallback: indic-transliteration (ITRANS/phonetic) or a tiny LLM call, cached per name
    # 3. validation: result must be Devanagari-only (U+0900–U+097F + space)
    # 4. on failure: name_dev = None  -> agents use आप, never the placeholder
```

### 2.2 Dominant-language detection
```python
def caller_lang(text: str) -> Lang | None:
    tokens = [t for t in tokenize(text) if t.lower() not in ACK_WORDS]  # ok, yes, haan, हाँ, जी, hmm...
    if len(tokens) < 2:
        return None                          # too short → no vote
    dev = sum(is_devanagari(t) for t in tokens)
    lat = len(tokens) - dev
    # romanised Hindi ("kal kar dunga") counts as HINDI:
    lat_hindi = sum(t.lower() in ROMAN_HINDI_LEXICON for t in tokens if not is_devanagari(t))
    hindi = dev + lat_hindi
    return Lang.HINDI if hindi >= (len(tokens) - hindi) else Lang.ENGLISH
```

```python
def observe_caller_language(state, text):
    if (req := explicit_switch_request(text)):
        state.language, state.language_locked = req, True
        return
    if state.language_locked:
        return
    if (l := caller_lang(text)) is not None:
        state.caller_lang_history.append(l)
        state.language = l                   # mirror during turns 1–3
    if state.turn_no >= 3:
        state.language_locked = True         # lock the turn-3 language
```

### 2.3 Explicit switch patterns
`in english`, `speak english`, `english please`, `english में`, `इंग्लिश में`, `hindi में बोलो`, `हिंदी में`, `speak hindi`.

## 3. Shared style snippet
S1 owns the `{{SHARED_RULES}}` prompt block ([02 §9](../02-shared-conversation-rules.md#9-prompt-block-inject-verbatim-as-shared_rules)) and versions it, so every agent uses the same version.

## 4. Test vectors
| Input sequence (caller) | Expected language per bot turn |
|---|---|
| "haan bolo" / "kitna hai" / "kal karunga" | H, H, H → locked H |
| "Yes speaking" / "What is this about" / "I will pay tomorrow" | E, E, E → locked E |
| E, E, E, then "हाँ" | stays E (ack word) |
| H, H, H, then "please speak in English" | switch to E, locked |
| "ok" at turn 1 | no vote → default H (T1 is always H) |
