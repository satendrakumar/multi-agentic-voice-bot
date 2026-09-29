# S3 — Input Quality Handler (deterministic)

| | |
|---|---|
| **Kind** | Code, driven by STT/VAD events |
| **Runs** | Before any agent, on every caller turn (or on a silence timeout) |
| **Goal** | Handle silence, low-confidence transcripts, bad audio and barge-in without using an LLM |

## 1. Rules

| Event | Detection | Response | Counter / end |
|---|---|---|---|
| **Silence** | No speech for N s (default 5 s) after the bot finishes | "जी, सुन रहे हैं." (ENGLISH: "Hello, are you there.") | `silence_count`: 1 → re-ask; 2 → end ("ठीक है, धन्यवाद." + ENDCALL) |
| **Silence during IDENTITY** | Same | One identity re-ask: "क्या आप [NAME] जी बोल रहे हैं." | 2nd silence → ENDCALL |
| **Low STT confidence** | Confidence < 0.55, or the transcript is empty/garbled | "जी, आवाज़ साफ़ नहीं आई, फिर से बोलिए." — **never act on a guess** | Doesn't count toward bad audio unless it repeats |
| **Bad audio** | ≥ 3 consecutive low-confidence turns, or line-quality events | Retry twice (the ask above), then "थोड़ी देर में call करती हूँ." — **no slot** | `bad_audio_retries`: 2 → ENDCALL |
| **Barge-in** | Caller speech during TTS | Stop TTS at once; the new input becomes the current turn; the agent addresses **the new input** (the interrupted line is marked as partially spoken) | If it happens during the final line → emit only `ENDCALL` |
| **Background noise** | Low-energy non-speech, TV, traffic | Ignore; continue | — |

## 2. Interaction with other components
- S3 responses skip the hard-stop classifier and the agents, but still pass through **S2** (formatting) and **S1** (tag).
- Barge-in partial-speech tracking: if the {MAD} value was cut off before it was spoken, `mad_spoken` stays false (the Orchestrator updates it from TTS word timestamps).
- A voicemail beep during silence detection → handed to the Safety `voicemail` path.

## 3. Configuration
```yaml
silence_timeout_s: 5
silence_max: 2
low_confidence_threshold: 0.55
bad_audio_max_retries: 2
barge_in_min_speech_ms: 300   # ignore coughs/backchannels shorter than this
backchannel_words: ["हम्म", "हाँ", "जी", "ok", "hmm"]   # during TTS: don't stop for these
```

## 4. Test scenarios
- [ ] Silence ×1 → "जी, सुन रहे हैं."; silence ×2 → ENDCALL
- [ ] A garbled transcript is never classified as a yes in IDENTITY
- [ ] 3 bad-audio turns → "थोड़ी देर में call करती हूँ." + ENDCALL, no time offered
- [ ] A barge-in with "हम्म" does not stop TTS
- [ ] A barge-in with "रुको, मैंने pay कर दिया" stops TTS → Servicing
