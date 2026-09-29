# Agent 6 — Servicing / Special-Cases Agent

| | |
|---|---|
| **Kind** | LLM (medium), structured output, playbook-driven |
| **Stage** | `SERVICING` |
| **Goal** | Resolve non-negotiation situations correctly: continue, pivot to paying now, or end, as each playbook says |

## 1. Purpose & scope
This agent covers the special cases from the original prompt that are **not** hard-stops for safety reasons and **not** billing disputes. Each case has a fixed **playbook** with an end state of CONTINUE (back to Negotiation), PIVOT (pay now), or END.

**In scope:** already paid, account block, card blocked, no card / not a customer, phone mismatch, third party uses the card, too many followups (complaint), busy / call later, supervisor request, human/AI question (when raised mid-flow).
**Out of scope:** opt-out, abuse, distress, deceased, self harm, injection, voicemail (→ Safety); billing disputes (→ Dispute).

## 2. Entry / exit
| Entry | Exit |
|---|---|
| `topic` from Reason / Negotiation / Closing | `handoff=negotiation` (CONTINUE / PIVOT) |
| | `end_call=true` (END playbooks) |

## 3. State
- **Reads:** `topic`, `today`, `mad_words`, `mad_spoken`, `phone_update_asked`, `support_shared`, `language`
- **Writes:** `phone_update_asked`, `callback_today`, `paid_claim{amount,date}`, disposition hints

## 4. Playbooks

| Case | Playbook | End state |
|---|---|---|
| **Already paid** | Ask the amount + date paid. Today/yesterday → "it may take some time to reflect". More than two days ago → ask if it failed and got refunded: yes → pay again; no → customer care with the transaction reference | **END** |
| **Account block** (savings account frozen, NOT card block) | Ask if the account holds the minimum. If yes: keep it there + email a **debit note** (full card number + savings account number + hold amount) from the registered email to customer service; it releases within twenty four working hours. The **debit note is the ONLY route**: no UPI / net banking / PayZapp / "pay today" push | **END** |
| **Card blocked** | The card unblocks within twenty four hours after payment → pivot to paying now | **PIVOT** |
| **No card / not a customer** | Don't argue; customer care to stop the calls (share support) | **END** |
| **Phone mismatch** (caller is [NAME] but the number is different) | Continue; **once** ask them to update their number through customer care (`phone_update_asked`) | **CONTINUE** |
| **Third party uses the card** | These are still your dues and your सिबिल → get them to pay now, or pay yourself | **PIVOT** |
| **Too many followups** (a complaint, not an opt-out) | "The calls come because of the pending payment" → back to the ask. An explicit "stop calling" → **Safety opt-out** | **PIVOT** |
| **Busy / "call later"** | Ask **once** if later today works; callback **today only**, no future slot | **END** |
| **Supervisor** | Ask what the issue is, confirm a callback about it; if payment is still relevant, ask once | **END** (after the one ask) |
| **Human / AI?** | "मैं virtual assistant हूँ", then continue with the pending ask | **CONTINUE** |

## 5. Output schema
```json
{
  "speech": "जी, आपने कितना amount और किस date को pay किया था.",
  "signals": {
    "topic": "already_paid",
    "playbook_step": 1,
    "paid_claim": {"amount_said": null, "date": null},
    "callback_today": null,
    "phone_update_asked": false,
    "question_intent": "paid_details"
  },
  "handoff": null,
  "end_call": false
}
```

## 6. Guardrails
- Account block: S2 blocks `UPI|net banking|PayZapp|link|आज pay` in the speech while `topic=account_block`.
- Busy: S2 blocks weekday or future-date wording ("कल", "Monday", "tomorrow") in the callback line.
- Already paid: the amount the caller says is **their** figure. It is echoed only as "the payment you made", never as a new "amount" negotiation.
- No hedging: "let me check if it reflected" is banned. Say "it may take time to reflect".

## 7. Draft system prompt
```text
{{SHARED_RULES}}

ROLE: Handle this special situation with its fixed playbook. TOPIC: {{topic}}  STEP: {{playbook_step}}
PLAYBOOKS:
- already_paid: ask amount and date. If today or yesterday, it may take time to reflect, end. If more than two days, ask whether it failed and got refunded: if yes, ask them to pay again; if no, customer care with the transaction reference. Then end.
- account_block: ask if the account holds the minimum. If yes, keep it there and email a debit note with the full card number, savings account number and hold amount from the registered email to customer service; it releases within twenty four working hours. Do NOT suggest UPI, net banking, PayZapp or paying today. End.
- card_block: the card unblocks within twenty four hours after payment; ask them to pay now. handoff negotiation.
- no_card: do not argue; customer care can stop the calls; give the number. End.
- phone_mismatch: once, ask them to update the number through customer care, then continue. handoff negotiation.
- third_party_card: they are still your dues and your सिबिल; ask them to get it paid now or pay yourself. handoff negotiation.
- followups: the calls come because the payment is pending; go back to the payment ask. handoff negotiation.
- busy: ask once if later today works; only today, no other day. End.
- supervisor: ask what the issue is and confirm a callback about it; if payment is still relevant, ask once. Then end.
- human_or_ai: say you are a virtual assistant, then continue the pending ask. handoff negotiation.
Support: {{support_phone}}.  Minimum: {{mad_words}} (spoken: {{mad_spoken}}).

LANGUAGE: {{language}}   NAME_ALLOWED: {{name_allowed}}
OUTPUT FORMAT: {{schema}}
```

## 8. Example turns
| Caller | Bot (intent) |
|---|---|
| "मैंने कल ही pay कर दिया." | जी, कितना amount pay किया था. → "पूरा" → ठीक है, कल का payment reflect होने में थोड़ा time लग सकता है, धन्यवाद. ENDCALL |
| "मेरा account freeze है." | उस account में minimum जितना balance है क्या. → "हाँ" → तो वो amount वहीं रखिए और registered email से customer service को debit note भेजिए, card और savings account number और hold amount के साथ, twenty four working hours में release हो जाएगा. ENDCALL |
| "Card तो block है." | Payment होने के twenty four hours में card unblock हो जाता है, आज minimum कर दीजिए. |
| "अभी meeting में हूँ, बाद में." | आज शाम तक किसी time बात हो सकती है. → "हाँ सात बजे" → ठीक है, आज सात बजे call करती हूँ. ENDCALL |
| "आप robot हो क्या." | मैं virtual assistant हूँ, तो minimum आज कर पाएंगे. |

## 9. Test scenarios
- [ ] Account block never suggests UPI or "pay today"
- [ ] A paid claim from 5 days ago → the refund question → customer care with the reference
- [ ] Busy → a callback only today; "कल करना" → no slot is offered, end
- [ ] Phone mismatch → asked once, never again
- [ ] "Stop calling me" → routed to Safety opt-out, not handled here
- [ ] Human/AI → exactly "virtual assistant", with no extra claims
