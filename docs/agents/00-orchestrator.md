# Agent 0 — Orchestrator / Call Controller

| | |
|---|---|
| **Kind** | Deterministic code (state machine). **Not an LLM.** |
| **Owns** | `CallState`, routing, context building, invariants, ENDCALL emission, fallback lines |
| **Runs** | On every turn, wrapped around every other agent |

## 1. Purpose & scope
The Orchestrator is the brain of the call **without being a model**. It decides which agent speaks, what that agent is allowed to see, and when the call ends. It enforces in code every rule that the model could otherwise forget.

**In scope:** stage transitions, state updates, context slicing (the identity lock), usage counters (angles, {MAD} spoken, questions asked), help-question tracking, ENDCALL, chained hops, error fallbacks, logging.
**Out of scope:** generating any caller-facing wording (except fallback lines taken from a fixed bank).

## 2. Entry / exit
- **Entry:** call connected → create `CallState`, run S1 transliteration, set `stage = IDENTITY`, invoke Agent 1 for T1.
- **Exit:** `stage = END` → emit the final speech + ` ENDCALL`, flush the call record (disposition, commitment, reason class) to CRM.

## 3. Per-turn algorithm

```python
def on_user_turn(state: CallState, stt: SttResult) -> str:
    # 1. input quality
    if (resp := S3.handle(state, stt)) is not None:
        return finalize(state, resp)                    # silence / low confidence / bad audio

    # 2. language (turns 1-3 mirror, then lock; explicit request switches)
    S1.observe_caller_language(state, stt.text)

    # 3. hard-stop pre-emption (classifier ran in parallel with context build)
    hs = hardstop_classifier(stt.text, state.stage)
    if hs.fires():
        state.prev_stage, state.stage = state.stage, Stage.SAFETY

    # 4. invoke active agent (max 1 chained hop)
    result = invoke(agent_for(state.stage), build_context(state, stt.text))
    apply(state, result)
    if result.handoff and not result.speech:
        state.prev_stage, state.stage = state.stage, stage_of(result.handoff)
        result = invoke(agent_for(state.stage), build_context(state, stt.text))
        apply(state, result)
    elif result.handoff:
        state.prev_stage, state.stage = state.stage, stage_of(result.handoff)  # takes effect next turn

    # 5. compliance guard, tag, ENDCALL
    speech = S2.guard(state, result.speech, regenerate=lambda fb: invoke(..., feedback=fb))
    return finalize(state, speech, end=result.end_call)

def finalize(state, speech, end=False):
    state.turn_no += 1
    out = S1.tag(state) + " " + speech
    if end:
        state.stage = Stage.END
        out += " ENDCALL"
    return out
```

## 4. Responsibilities in detail

### 4.1 Identity lock (hard, in code)
- `build_context()` includes `card_name`, `card_last4_words`, `out_words`, `mad_words` and `due_date_words` **only if** `identity_status == VERIFIED`.
- Only Agent 1's `signals.identity` can change `identity_status`, and only to VERIFIED when `signals.identity_evidence` holds an explicit self-identification (see Agent 1 §5).
- Moving to DISCLOSURE requires VERIFIED. There is no other path to the financial agents.

### 4.2 Stage routing
Implements the routing table in [00 §4](../00-architecture-overview.md#routing-table-orchestrator). When `handoff` is invalid for the current stage, it is ignored and logged.

### 4.3 Counters & usage tracking
| Counter | Updated when | Effect on context |
|---|---|---|
| `angles_used` | `signals.angle_used` set | `angles_remaining` = all − used |
| `angle_deepened` | `signals.angle_deepened` | That angle cannot be deepened again |
| `funds_ideas_used` | `signals.funds_idea_used` | `funds_ideas_remaining` |
| `mad_spoken` | S2 detects `mad_words` in the speech | Context flag tells the agent to say "the minimum" |
| `out_spoken` | S2 detects `out_words` | Same |
| `questions_asked` | `signals.question_intent` | Passed to the agent to avoid repeats |
| `callouts` | `signals.callout` | Negotiation escalates light → firm |
| `hardship_asks` | Negotiation in hardship mode asks | After 2, accept the best offer ≥ MAD |
| `ptp_history` | `signals.commitment.ptp_date` | Detect push-out (callout) vs pull-in (accept) |
| `abuse_warnings`, `injection_warnings` | Safety signals | Second occurrence → END |
| `help_asked` | Closing asks "कुछ और help" | Never asked twice |

### 4.4 Name permission
`name_allowed_this_turn = turn_no < 2 or expecting_end`, where `expecting_end` is true when the stage is CLOSING and `help_asked`, or the stage is SAFETY. S2 strips the name if it appears on a turn where it is not allowed.

### 4.5 ENDCALL
- Only the Orchestrator appends `ENDCALL`, as the last token, exactly once.
- If the caller barges in during a concluding line → emit just `ENDCALL` (the speech has already been heard or has been interrupted).

### 4.6 Negotiation exhaustion (feeds Closing)
`negotiation.exhausted` is true when **any** of these holds:
- A commitment has been captured (amount + date, with mode known or defaulted to "app").
- Refusal: one angle + one minimum push done with no movement.
- Hardship: 2 asks done → take the best offer ≥ MAD (or the date at MAD).
- Total negotiation turns ≥ 10 (safety valve).

### 4.7 CRM disposition (written at END)
`PTP_FULL`, `PTP_MIN`, `PAID_CLAIM`, `DISPUTE`, `WRONG_NUMBER`, `THIRD_PARTY`, `CALLBACK`, `REFUSED`, `NO_RESPONSE`, `HARDSTOP_<type>`, `OPT_OUT`, `ACCOUNT_BLOCK`, plus `reason_class`, `commitment` and `followup_date`.

## 5. Fallback line bank (examples)
| Stage | HINDI | ENGLISH |
|---|---|---|
| IDENTITY | क्या आप [NAME] जी बोल रहे हैं. | Am I speaking with [NAME] जी. |
| NEGOTIATION | आज minimum clear कर पाएंगे, हाँ या नहीं. | Can you clear the minimum today, yes or no. |
| CLOSING | ठीक है, धन्यवाद, आपका दिन शुभ हो. | Alright, thank you, have a good day. |

(These are the only fixed strings. They are used only after a failed regeneration.)

## 6. Test scenarios
- [ ] UNVERIFIED context contains no `out_words` / `card_last4_words` (unit test on `build_context`)
- [ ] `handoff=disclosure` from NEGOTIATION is rejected
- [ ] Angles: after "cibil" is used, the next context has no "cibil" in `angles_remaining`
- [ ] Chained hop: NEGOTIATION → DISPUTE in the same turn gives exactly one spoken line
- [ ] ENDCALL appears once, last, and nothing follows it
- [ ] Barge-in on the final line → output is just `ENDCALL`
- [ ] Negotiation turn cap (10) forces CLOSING
