# Agent 3 — Reason Discovery & Classification Agent

| | |
|---|---|
| **Kind** | LLM (medium), structured output |
| **Stage** | `REASON` (usually 1–2 bot turns) |
| **Goal** | Apply the **reason gate**: learn WHY the payment is pending, classify it once, and route |

## 1. Purpose & scope
The original prompt says: *"before accepting any promise, learn WHY it's pending — ask once if unclear. Vague agreement isn't a reason."* This agent owns that gate and the **first classification**. Every rebuttal strategy in Negotiation depends on this class.

**In scope:** interpreting the reply to T2, asking the reason (once), classifying, spotting firm-today commits, spotting lever and servicing topics.
**Out of scope:** rebutting or pushing amounts (Negotiation), explaining levers (Dispute).

## 2. Entry / exit
| Entry | Exit (handoff) |
|---|---|
| The caller's first reply after T2 | `firm_today` → **closing** (no restating) |
| | `willing / hardship / stalling / refusal` → **negotiation** |
| | `wrong_amount / statement_not_received` or a lever topic (settlement, waiver, EMI, unknown figure) → **dispute** |
| | Servicing topic (already paid, account block, no card, busy…) → **servicing** |
| | Reason still unclear after one ask → **negotiation** with `unknown` |

## 3. State
- **Reads:** `recent_turns`, `reason_asked`, `language`
- **Writes:** `reason_class`, `reason_text`, `reason_asked`, and possibly `commitment` (on firm today)

## 4. Classification rules

| Class | Cues | Notes |
|---|---|---|
| `firm_today` | "आज कर दूँगा", "in a few hours", "by evening", "अभी करता हूँ" | The reason gate is **skipped**; go straight to Closing and do not re-confirm |
| `willing` | forgot, "ध्यान से निकल गया", "meant to pay", "busy था, भूल गया" | Genuine intent |
| `hardship` | job loss, business loss, salary delayed, "पैसे नहीं हैं", money crunch | **NOT** an active emergency (hospital, accident → Safety `distress`) |
| `stalling` | shopping, travel, "next week", "देखता हूँ", "बाद में", vague | |
| `refusal` | "नहीं करूँगा", "नहीं भरना", no reason given | |
| `wrong_amount` | "amount सही नहीं", "मैंने ये transaction नहीं किया", "इतना कैसे" | By **meaning**, not keywords |
| `statement_not_received` | "statement नहीं आया", "bill ही नहीं मिला" | |
| `unknown` | Vague agreement ("हाँ हाँ कर दूँगा") with no reason and no date | Ask the reason **once** |

### Gate logic
```
reply to T2
 ├─ firm TODAY commit?                        → firm_today → Closing
 ├─ hard-stop?                                → (classifier pre-empts → Safety)
 ├─ servicing / lever topic?                  → handoff (topic)
 ├─ reason stated?                            → classify → Negotiation / Dispute
 └─ no reason (vague / "कर दूँगा" / "कब तक")  →
        reason_asked == false → ask WHY once (a single question) → stay in REASON
        reason_asked == true  → unknown → Negotiation
```

### Holding the class
The first classification **sticks**. Re-classification happens only on an explicit contradiction (e.g. first "forgot", later "actually I lost my job"). This agent sets the initial class. Negotiation can raise `reason_contradiction=true` with a new class, and the Orchestrator accepts it only once.

## 5. Output schema
```json
{
  "speech": "किस वजह से payment pending रह गया.",
  "signals": {
    "reason_class": "unknown",
    "reason_text": null,
    "topic": null,
    "commitment": {"firm_today": false, "amount": null, "ptp_date": null, "mode": null},
    "question_intent": "reason"
  },
  "handoff": null,
  "end_call": false
}
```
When the class is known on the first reply, the speech is **empty** and the target agent speaks this turn (a chained hop). That way the reason is not acknowledged with filler.

## 6. Guardrails
- Reason and payment asks go on **separate** turns. The reason question contains no amount push.
- No empathy on hardship. The hardship class hands off to Negotiation with no line of its own.
- Ask the reason at most once (`reason_asked`).

## 7. Draft system prompt
```text
{{SHARED_RULES}}

ROLE: The customer has just heard their dues. Your job is only to understand WHY the payment is pending and classify it.
Classes: firm_today, willing, hardship, stalling, refusal, wrong_amount, statement_not_received, unknown.
- An active emergency (hospital, surgery, accident, death) is NOT hardship; the system handles it separately.
- If they commit to paying TODAY (including "in a few hours", "by evening"): class firm_today, speech empty.
- If a reason is stated: classify it, speech empty, and handoff to "negotiation" (or "dispute" for wrong_amount, statement_not_received, settlement, waiver, EMI, unknown charges; or "servicing" for already paid, account block, no card, busy or call later, supervisor).
- If no reason is given and REASON_ASKED is false: ask ONE short question about why the payment is pending. No amount push in that question.
- If REASON_ASKED is true and still no reason: class unknown, speech empty, handoff "negotiation".

LANGUAGE: {{language}}   REASON_ASKED: {{reason_asked}}
OUTPUT FORMAT: {{schema}}
```

## 8. Example turns
| Caller reply to T2 | Result |
|---|---|
| "हाँ कर दूँगा." | Ask: "जी, payment अब तक pending क्यों रह गया." (`unknown`, `reason_asked=true`) |
| "Salary नहीं आई अभी." | `hardship`, → Negotiation (empty speech) |
| "Goa गया था, next week कर दूँगा." | `stalling`, → Negotiation |
| "भूल गया था." | `willing`, → Negotiation |
| "शाम तक कर देता हूँ." | `firm_today`, → Closing |
| "ये amount गलत है." | `wrong_amount`, → Dispute |
| "मैंने already pay कर दिया." | topic `already_paid`, → Servicing |

## 9. Test scenarios
- [ ] "हाँ हाँ कर दूँगा" is not accepted as a reason → asked once
- [ ] A second vague reply → `unknown` → Negotiation (no second reason ask)
- [ ] "by evening" → Closing, no re-confirm
- [ ] "papa hospital में हैं" → pre-empted by Safety, never classified as hardship
- [ ] "job चली गई" → hardship, no empathy line spoken
- [ ] Class stays fixed across later turns unless contradicted
