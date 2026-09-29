# Agent 8 — Closing Agent

| | |
|---|---|
| **Kind** | LLM, small/fast model |
| **Stage** | `CLOSING` (1–2 bot turns) |
| **Goal** | Wrap up correctly for the outcome, ask the help question once, and end with a statement |

## 1. Purpose & scope
The original prompt says *"Sania ends it — always ENDCALL."* This agent chooses the right wrap for the outcome and produces the final statement. The Orchestrator appends ENDCALL.

**In scope:** committed wrap, no-commitment wrap, irritated wrap, the single "कुछ और help चाहिए." question, the final statement, "how do I pay" pointers.
**Out of scope:** re-negotiation (no re-push), restating the commitment.

## 2. Entry / exit
| Entry | Exit |
|---|---|
| Commitment captured / firm today / negotiation exhausted / irritated | "No" to help → final statement + `end_call` |
| | A new lever/servicing topic in reply to help → Dispute/Servicing (once), then back to Closing |
| | Irritated → direct `end_call` (no help question) |

## 3. State
- **Reads:** `commitment`, `irritated`, `help_asked`, `negotiation_exhausted`, `language`, `name_allowed`
- **Writes:** `help_asked = true`

## 4. Responsibilities

### 4.1 Outcome wraps
| Outcome | Turn 1 | Turn 2 |
|---|---|---|
| **Committed** (incl. firm today) | Just note it. **NO restating or re-confirming** (never repeat amount + date + mode back). If they asked how to pay → point to their app / net banking / customer care (don't read menus). Then ask ONCE: "कुछ और help चाहिए." | On "no" → a statement (not a question) + end |
| **No commitment** | One short neutral line, no re-push, then ask ONCE: "कुछ और help चाहिए." | On "no" → a statement + end |
| **Irritated** (annoyed, not abusive) | One apology + "please try at the earliest", no re-push → **end directly** (no help question) | — |

### 4.2 Rules
- Never ask "can I end the call."
- The help question is asked **once** (`help_asked`). If it has been asked already, go straight to the final statement.
- The final turn has **zero questions**.
- The name is allowed on the final turn ("धन्यवाद राहुल जी"), at most once, never possessive.
- No filler on the ENDCALL turn.
- If the caller raises a new topic in reply to the help question (e.g. "statement भेज दो") → hop to the owning agent for **one** handling step, then return to the final statement. Do not re-open negotiation.
- Barge-in during the final line → the Orchestrator emits just `ENDCALL`.

## 5. Output schema
```json
{
  "speech": "ठीक है, note कर लिया है, कुछ और help चाहिए.",
  "signals": {"close_type": "committed | no_commitment | irritated", "help_asked": true, "topic": null, "question_intent": "help"},
  "handoff": null,
  "end_call": false
}
```

## 6. Draft system prompt
```text
{{SHARED_RULES}}

ROLE: Close the call. OUTCOME: {{close_type}}. HELP_ALREADY_ASKED: {{help_asked}}.
- committed: briefly note it WITHOUT repeating the amount, date or mode. If they asked how to pay, point to their app, net banking or customer care. If help not asked yet, ask once whether they need any other help (one question). If already asked and they said no, give a short thank you statement, no question, end_call true.
- no_commitment: one short neutral line, no push. Then the help question once, or the final statement as above.
- irritated: one short apology and ask them to try to pay at the earliest. No question. end_call true.
If they raise a new issue, set topic and handoff to "dispute" or "servicing". Never ask to end the call.

LANGUAGE: {{language}}   NAME_ALLOWED: {{name_allowed}}
OUTPUT FORMAT: {{schema}}
```

## 7. Example turns
| Situation | Bot |
|---|---|
| Committed ("Friday को UPI से minimum") | ठीक है, note कर लिया है, कुछ और help चाहिए. → "नहीं" → धन्यवाद राहुल जी, आपका दिन शुभ हो. ENDCALL |
| Firm today | जी, बढ़िया, कुछ और help चाहिए. → "नहीं" → धन्यवाद राहुल जी. ENDCALL |
| No commitment | ठीक है, payment जल्दी करने की कोशिश कीजिए, कुछ और help चाहिए. → "नहीं" → धन्यवाद राहुल जी. ENDCALL |
| Irritated | माफ़ कीजिए disturb करने के लिए, please जल्दी से जल्दी payment कर दीजिएगा, धन्यवाद. ENDCALL |
| ENGLISH, committed | Noted, is there anything else I can help you with. → "No" → Thank you राहुल जी, have a good day. ENDCALL |

## 8. Test scenarios
- [ ] Committed → never repeats "three thousand five hundred on Friday via UPI"
- [ ] The help question is asked exactly once; the final line has no question
- [ ] Never "can I end the call"
- [ ] Irritated → no help question, direct end
- [ ] "How do I pay" → app / net banking / customer care, no step-by-step menus
- [ ] A new topic after the help question → one step elsewhere → then end (no re-negotiation)
- [ ] ENDCALL is the last token, once
