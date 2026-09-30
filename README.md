# multi-agentic-voice-bot

A multi-agent version of the **Sania** HDFC credit-card collections voice bot (Hinglish/English, cascaded STT → LLM → TTS). The single large prompt is split into focused agents, and the compliance rules are enforced in code.

## Run

```bash
uv sync
cp .env.example .env           # all settings live here (real env vars override it)
vllm serve Qwen/Qwen3.5-4B --port 8000   # default LLM: any OpenAI-compatible server
uv run python main.py          # text simulator: you type as the caller, an empty line = silence
uv run pytest                  # unit tests (fake LLM, no API calls)
```

The LLM is reached through `sania/llm/client.py:LLMClient` (standard OpenAI SDK, streamed, JSON via `response_format` json_schema), so vLLM, OpenAI or any compatible server works by changing `SANIA_LLM_BASE_URL` / `SANIA_MODEL`. `SANIA_LLM=claude` switches to the Anthropic API instead.

### Voice mode (microphone + speaker)

```bash
uv sync --extra voice          # torch, transformers, kokoro, silero-vad, pyrnnoise, sounddevice ...
brew install espeak-ng         # Kokoro's Hindi phonemes (Linux: apt install espeak-ng)
hf auth login                  # only for the gated alternatives (indic_parler, indic_conformer)
uv run python main.py --voice
```

Pipeline: mic → endpointing → **noise removal → VAD speech chunks** → STT (per chunk, joined) → Orchestrator → TTS (piece by piece) → speaker.

| Stage | Default (`SANIA_*` name) | Alternatives | Code |
|---|---|---|---|
| Noise removal | xiph RNNoise via `pyrnnoise` (`rnnoise`) | `noisereduce`, `none` | `sania/voice/rnnoise.py` |
| Speech chunks | Silero VAD (`silero`): speech only, merged up to 15 s | `energy` | `sania/voice/silero.py` |
| STT | `openai/whisper-large-v3-turbo` (`whisper`): auto language, Hindi retry on Urdu script | `indic_conformer` | `sania/voice/whisper.py` |
| TTS | `hexgrad/Kokoro-82M` (`kokoro`; voices hf_alpha / af_heart, 24 kHz) | `indic_parler` | `sania/voice/kokoro.py` |
| Audio I/O | `sounddevice` with energy-based endpointing | | `sania/voice/audio_io.py` |

**Swapping a model:** implement the matching protocol, add it to the table in `sania/voice/registry.py`, and select it by name.

| To swap | Protocol | Registry table | Setting |
|---|---|---|---|
| STT | `SpeechToText.transcribe(audio, lang)` in `sania/voice/interfaces.py` | `STT_MODELS` | `SANIA_STT` |
| TTS | `TextToSpeech.synthesize(text, lang)` in `sania/voice/interfaces.py` | `TTS_MODELS` | `SANIA_TTS` |
| Denoiser | `Denoiser` in `sania/voice/preprocess.py` | `DENOISERS` | `SANIA_DENOISER` |
| VAD chunker | `Chunker` in `sania/voice/preprocess.py` | `VADS` | `SANIA_VAD` |

Noise removal and chunking wrap any STT model automatically.

For a telephony stack instead of the local mic, implement `AudioIO` (or call `Orchestrator.start()` once, then `Orchestrator.respond(transcript, confidence)` per caller turn). Each reply starts with `<|HINDI|>` or `<|ENGLISH|>` (this picks the TTS voice) and ends with `ENDCALL` on the last turn.

### Settings (`.env` or environment variables; see `.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `SANIA_LLM` | `openai` | `openai` (any OpenAI-compatible server) or `claude` |
| `SANIA_MODEL` | `Qwen/Qwen3.5-4B` (`claude-opus-5-5` for claude) | Model for all agents |
| `SANIA_FAST_MODEL` | same as `SANIA_MODEL` | Model for identity, disclosure, closing and the hard-stop classifier |
| `SANIA_LLM_BASE_URL` | `http://localhost:8000/v1` | OpenAI-compatible server URL |
| `SANIA_LLM_API_KEY` | `EMPTY` | Server API key, if it needs one |
| `SANIA_LLM_MAX_TOKENS` | `1024` | Max output tokens per call (prompt + this must fit `max_model_len`) |
| `SANIA_LLM_THINKING` | unset | `1`/`0` sends Qwen's `enable_thinking` switch; leave unset for other servers |
| `SANIA_STT` / `SANIA_TTS` | `whisper` / `kokoro` | Voice models, by name in `sania/voice/registry.py` |
| `SANIA_DENOISER` | `rnnoise` | Noise removal before STT: `rnnoise`, `noisereduce`, `none` |
| `SANIA_VAD` | `silero` | Speech chunking: `silero`, `energy` |
| `SANIA_MAX_CHUNK_S` | `15` | Longest audio chunk sent to STT |

## Prompts

All prompt text lives in versioned folders under [`prompts/`](prompts/README.md) (one `.md` per agent, plus shared rules, classifier, and negotiation move texts). Pick a version with `SANIA_PROMPT_VERSION`. To try a change, copy the folder to a new version and compare with:

```bash
uv run python scripts/simulate_calls.py                          # replay scripted callers on the real LLM
SANIA_PROMPT_VERSION=v2 uv run python scripts/simulate_calls.py hardship
```

## Code layout

```
sania/
  orchestrator.py      Agent 0: state machine, routing, identity lock, counters, ENDCALL
  agents/
    base.py            Agent base class (role prompt + signals schema -> AgentResult)
    identity.py        Agent 1: greeting and identity verification (+ rule-based second key)
    disclosure.py      Agent 2: recorded line, card, outstanding, due date, "pay today"
    reason.py          Agent 3: why is it pending, classified once
    negotiation.py     Agent 4: full -> minimum -> near date, angles, funds, promise date
    dispute.py         Agent 5: wrong amount, settlement, waiver, EMI, statement, support info
    servicing.py       Agent 6: already paid, account/card block, callback, supervisor
    safety.py          Agent 7: hard-stop classifier + safe responder
    closing.py         Agent 8: wrap-up, one help question, final statement
  language.py          S1: name transliteration, language mirror/lock, TTS tag
  guard.py             S2: auto-fixes + hard checks on every reply
  input_quality.py     S3: silence and low-confidence audio
  numbers.py           money / digit / date to English words
  state.py             CallState, Profile, topic lists
  prompts.py           loads prompts/<version>/*.md and *.toml; support contacts
  llm/
    __init__.py        LLM interface, get_llm() backend switch, JSON-schema helpers
    client.py          LLMClient: OpenAI-compatible servers (vLLM by default)
    claude.py          Anthropic Claude backend
  voice/
    interfaces.py      SpeechToText / TextToSpeech / AudioIO protocols (the swap point)
    registry.py        model name -> implementation
    preprocess.py      PreprocessedSTT wrapper, Denoiser/Chunker protocols, simple fallbacks
    rnnoise.py, silero.py, whisper.py, kokoro.py, indic_*.py   one adapter per model
    session.py         call loop: record -> STT -> bot -> TTS -> play
```

## Design docs
- [Architecture overview](docs/00-architecture-overview.md): agent list, RACI, state machine, pipeline, latency
- [Shared state & contracts](docs/01-shared-state-and-contracts.md)
- [Shared conversation rules](docs/02-shared-conversation-rules.md)
- [Evaluation plan & coverage matrix](docs/03-evaluation-plan.md)
- Agents: [`docs/agents/`](docs/agents/) · Services: [`docs/services/`](docs/services/)
