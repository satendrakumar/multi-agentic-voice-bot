# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A multi-agent rewrite of "Sania", an HDFC credit-card collections voice bot (Hinglish/English, cascaded STT → LLM → TTS). The original single big prompt was split into 8 agents + 3 code services. The design docs in `docs/` are the spec. `docs/03-evaluation-plan.md` §4 maps every rule of the original prompt to the agent or service that owns it, so check it before moving a rule between components.

## Commands

```bash
uv sync                                   # install deps (Python 3.13, uv)
uv run pytest                             # all tests (fake LLM, no API calls, <1s)
uv run pytest tests/test_services.py::test_money_words_reads_every_place   # single test
uv run python main.py                     # interactive text simulator (needs the LLM server from .env); empty line = silence
uv sync --extra voice && uv run python main.py --voice   # mic/speaker; Kokoro's Hindi needs espeak-ng installed
```

`tests/test_voice.py` is skipped unless the `voice` extra is installed (`pytest.importorskip("numpy")`).

```bash
uv run python scripts/simulate_calls.py [scenario ...]   # replay scripted callers on the real LLM (prompt tuning)
```

**Prompts live in `prompts/<version>/`, not in code** (`SANIA_PROMPT_VERSION`, default `v1`; see `prompts/README.md`).
- `sania/prompts.py:load(name)` reads `<name>.md`; `Agent.instructions` is `load(agent.name)`, and `system_prompt()` prepends `shared.md`.
- Negotiation move texts are in `negotiation_moves.toml`.
- Change prompts by adding a new version folder, not by editing a released one. `tests/test_prompts.py` checks every version has all files.
- Prompt examples use `<name>`; `guard.autofix` replaces it with the real name.

Settings are read by `sania/config.py` from the environment and a repo-root `.env` (template: `.env.example`, which documents every variable).
- The default LLM is `SANIA_LLM=openai`: any OpenAI-compatible server at `SANIA_LLM_BASE_URL`, locally vLLM serving `Qwen/Qwen3.5-4B` on port 8000 with `max_model_len` 8192.
- `SANIA_LLM=claude` uses the Anthropic API instead.

There is no linter or formatter configured.

## Architecture

**Per-turn flow (`sania/orchestrator.py`, plain code, no LLM):** `input_quality.handle` (silence / low STT confidence, answered without an LLM) → `language.observe` → the hard-stop classifier runs in a thread **in parallel with** the current stage's agent; if it fires, the agent's result is discarded and `SafetyAgent` runs instead → `_update_state` turns the agent's `signals` into `CallState` changes → handoff → `_final_speech` (guard autofix + check → regenerate once with feedback → the agent's `fallback()` line) → `_say` adds the language tag and `ENDCALL`.

**Key contracts:**
- Agents (`sania/agents/*.py`, subclasses of `agents/base.py:Agent`) are stateless: a static `instructions` prompt, a `signals_schema`, a `handoffs` tuple, and optional `extra()` / `validate()` / `fallback()`. They return `AgentResult(speech, signals, handoff, end_call)`. Only the Orchestrator mutates `CallState` (`sania/state.py`).
- **An empty `speech` plus a `handoff` means a chained hop**: the target agent speaks in the same turn (max one hop). A handoff *with* speech takes effect on the next turn.
- The system prompt is `"AGENT: <name>\n\n" + SHARED_RULES + instructions`, and all dynamic data goes in the user message as JSON (keeps the system prompt stable for caching). `tests/conftest.py:FakeLLM` routes scripted replies by parsing that `AGENT:` first line, so keep that prefix.
- LLM calls go through the callable returned by `sania/llm/__init__.py:get_llm()`, with signature `(system, user, schema, effort, model) -> dict | None`. `None` means failure, and the caller uses the agent's fallback line.
- `llm/client.py:LLMClient` uses the standard OpenAI SDK with `stream=True`. It sends `response_format` json_schema, repeats the schema in the prompt, and uses `parse_json` to tolerate `<think>`, code fences and missing keys.
- `llm/claude.py` is the Anthropic backend. `effort` only affects Claude.
- Every schema must be strict (all properties required, `additionalProperties: false`); use the `obj`/`nullable`/`enum` helpers.
- The reply is spoken only after the complete JSON has passed the guard. Don't stream partial `speech` to TTS; that would bypass the identity-lock and amount checks.

**Compliance is enforced in code, not only in prompts. Don't move these rules back into prompts:**
- Identity lock: `_context()` leaves out all account data until `state.verified`. Verification needs both the model's `VERIFIED` signal **and** `identity.py:looks_like_self_id()`. `guard.check` also blocks account words while unverified.
- Only two amounts (`{OUT}`, `{MAD}`): account values reach the agents already converted to words (`Profile.spoken()`, `numbers.py`). `guard.check` rejects any other rupee figure. The `out_spoken`/`mad_spoken` flags are set from the final speech.
- Code tracks the "use once" rules: angles, funds ideas, callouts, the help question, abuse/injection warnings.
- `ENDCALL` is appended only by `_say`, and agents' speech is stripped of tags and `ENDCALL` by `guard.autofix`.
- Name usage is decided by `_name_allowed()` (always allowed in the IDENTITY/SAFETY stages; otherwise only turns 0–1 and the final closing turn). `autofix` removes the name on other turns.

**Voice layer (`sania/voice/`):**
- `VoiceSession` depends only on the protocols in `interfaces.py`. Model adapters import torch, transformers and parler-tts **inside `__init__`**, so the core package and tests don't need the `voice` extra; keep it that way.
- `registry.build_stt` always wraps the STT model in `preprocess.PreprocessedSTT`: denoiser (default RNNoise) → chunker (default Silero VAD) → STT per chunk → joined text. An empty transcript is what the Orchestrator treats as silence.
- Denoisers, chunkers, STT and TTS are each picked by name from registry tables.
- `Audio.resample()` does all sample-rate conversion: RNNoise runs at 48 kHz, and Silero and Whisper at 16 kHz.
- `rnnoise.py` calls pyrnnoise's low-level `create`/`process_mono_frame`/`destroy` directly, because its `RNNoise` class pulls in an extra audio-graph dependency.
- Whisper auto-detects the language per chunk and re-runs with `language="hindi"` if the output is in Urdu script.
- The reply's `<|HINDI|>`/`<|ENGLISH|>` tag picks the TTS voice (`session.split_reply`, which also strips `ENDCALL`). `_speak` synthesizes the next piece while the current one plays.
- The default voice stack is Whisper large-v3-turbo (STT) and Kokoro-82M (TTS; one `KModel` shared by the Hindi `h` and English `a` pipelines).
- IndicConformer and Indic Parler-TTS are registered alternatives. parler-tts pins `transformers==4.46.1` for the whole environment.

**Small-model design:** the default LLM is a 4B local model, so decisions are made in code and the model mostly phrases.
- `negotiation.next_move()` picks the move from state (minimum pivot → stall callout → angles alternating with funds ideas → date). The model reports it back in `signals.move_done`, and `_update_negotiation` records it.
- Rules the small model breaks are enforced in `guard.check`: false payment claims, masculine self-reference, agreeing the amount is wrong, promising calls will stop.
- Closing: a help question never ends the call.
- Opt-out needs stop-calling words as well as the classifier's label.
- Language locks after 3 caller replies that indicate a language.

**Adding or changing an agent:** update its class, then the `Stage` enum + `self.agents` map if it's new, `config.EFFORT` (and `FAST_AGENTS` if relevant), and its `_update_state` branch if it emits new signals. Put per-agent output checks in `validate()`, not in `guard.py`.

## Conventions for spoken output
Rules in `sania/prompts.py:SHARED_RULES` and `docs/02-shared-conversation-rules.md`:
- Only `.` and `,` in speech (no `?`).
- Numbers as English words: money place by place, identifiers digit by digit.
- Banking words in Latin script inside Hinglish.
- No empathy or hedging phrases.
- The language locks after bot turn 3.

When you change `guard.py`, re-check that the real support strings and account values still pass. The length check deliberately ignores them.
