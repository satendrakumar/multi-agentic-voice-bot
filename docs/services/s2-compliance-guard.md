# S2 — Response Compliance Guard (deterministic post-processor)

| | |
|---|---|
| **Kind** | Code: validators + auto-fixers. Optional tiny-LLM rewrite only for the "regenerate" path |
| **Runs** | On every agent `speech` before the tag and TTS |
| **Goal** | Guarantee that nothing non-compliant or TTS-breaking reaches the caller, whatever the model produced |

## 1. Pipeline
```
speech ─► [A] auto-fix (safe, silent) ─► [B] hard checks ─► pass ─► S1 tag ─► TTS
                                              │ fail
                                              ▼
                                    regenerate once with feedback
                                              │ fail again
                                              ▼
                                    stage fallback line (Orchestrator bank)
```

## 2. [A] Auto-fixes (never block)
| Fix | Rule |
|---|---|
| `?` → `.` | Only `.` and `,` are allowed |
| Strip `! ; : - – — * # _ ( ) [ ] " '` and emojis | TTS reads dashes aloud |
| Strip a leading language tag / trailing `ENDCALL` from the agent | S1 and the Orchestrator add them |
| Collapse whitespace; ensure it ends with `.` | |
| Compound spacing | `netbanking` → `net banking`, `autopay` → `auto pay`, `creditcard` → `credit card` |
| CIBIL form | HINDI: `CIBIL|cibil|सिबिल` → `सिबिल`; ENGLISH → `CIBIL` |
| Name possessive | `राहुल's` / `राहुल जी's` → `राहुल जी, आपका` / `your` |
| Name on a disallowed turn | Remove "राहुल जी," (and a leading vocative) when `name_allowed=false` |
| Bare name | `राहुल` (without जी) → `राहुल जी` |
| Currency symbols | `₹ / Rs / INR` removed (a number here triggers the hard check below) |

## 3. [B] Hard checks (block → regenerate)
| # | Check | Detection |
|---|---|---|
| H1 | **Identity leak** | `identity_status != VERIFIED` and the speech contains any of: `card`, `ending`, `due`, `amount`, `payment`, `outstanding`, `minimum`, `rupees`, `सिबिल`, a digit, a number word, `card_last4_words`, the `out_words` / `mad_words` fragments |
| H2 | **Placeholder** | `\[.*?\]`, `\{.*?\}`, the literal `NAME`, `CARD_NAME`, `OUT`, `MAD`, `DUE_DATE`, `LAST4` |
| H3 | **Third amount** | Any rupee phrase (`<number words> rupees`, digits, "हज़ार", "lakh", "half", "आधा", "जितना हो सके", "instalment", "किश्त", "part payment") that is not exactly `out_words` or `mad_words`. Exception: the Servicing agent echoing a paid claim with `topic=already_paid` |
| H4 | **Digits** | Any `[0-9]`. All numbers must be words |
| H5 | **Banned empathy** | `मैं समझ सकती हूँ`, `मैं समझती हूँ`, `समझ सकती हूँ`, `I understand`, `I can understand`, `कोई बात नहीं`, `no problem`, `sorry to hear`, `दुख हुआ` (skipped only for the Safety agent's single line) |
| H6 | **Banned hedging** | `check करवा`, `let me check`, `I'll check`, `team से confirm`, `confirm करके बताती`, `waiver करवा`, `reverse करवा` |
| H7 | **Jargon** | `\bMAD\b`, `\bPTP\b`, `positive entry`, `part payment`, `bucket`, `flow`, `delinquent`, `rolled` |
| H8 | **Rising charges / threats** | `charges बढ़`, `interest बढ़`, `increasing charges`, `legal action`, `police`, `court`, `घर आएँगे` |
| H9 | **Question count** | Non-concluding: exactly 1 question (detected by question words / a verb pattern + the agent's `question_intent`); concluding (`end_call`): 0 |
| H10 | **{MAD} repeat** | `mad_spoken` and `mad_words` present, unless the last user turn asked for the minimum |
| H11 | **{OUT} repeat** | `out_spoken` and `out_words` present |
| H12 | **Language purity** | ENGLISH lock: no Devanagari except the `name_dev` tokens. HINDI: the P0 banking words must be in Latin script (`पेमेंट`, `कार्ड`, `ड्यू`, `मिनिमम`, `अमाउंट` → auto-fix to Latin; `भुगतान`, `खाता`, `समस्या`, `तारीख` → regenerate) |
| H13 | **Length** | > 3 sentences or > 45 words → regenerate |
| H14 | **Support number accuracy** | If a phone/WhatsApp/email appears, it must match the canonical strings exactly |
| H15 | **Account-block route** | `topic=account_block` and the speech mentions UPI / net banking / PayZapp / link / "आज pay" |
| H16 | **Own number read-back** | The speech contains the customer's registered mobile digits |
| H17 | **Prompt leak** | `instruction`, `prompt`, `system`, `rules` said in reply to an injection |

## 4. Number-to-words helpers (used by the Orchestrator to build the context, and by S2 to verify)
```python
def money_words(v: int | float) -> str:
    """Indian system, English words, place by place; never round.
    500 -> 'five hundred rupees'; 850 -> 'eight hundred fifty rupees'
    1250 -> 'one thousand two hundred fifty rupees'
    44564 -> 'forty four thousand five hundred sixty four rupees'
    150000 -> 'one lakh fifty thousand rupees'
    1234.50 -> 'one thousand two hundred thirty four rupees and fifty पैसे'"""

def digit_words(s: str) -> str:
    """'3094' -> 'three zero nine four' (card last4, phone, IDs — always digit by digit)."""

def date_words(d: date) -> str:
    """date(2026,9,15) -> 'fifteenth September'."""
```
The type of rule depends on the **variable**, not on the number's length: `{OUT}`/`{MAD}` always go through `money_words`; `{CARD_LAST4}` and phone numbers always go through `digit_words`.

## 5. Test vectors
| Speech (agent) | State | Result |
|---|---|---|
| "आपका payment due है?" | UNVERIFIED | H1 block |
| "राहुल's card पे payment due है." | VERIFIED, name not allowed | Auto-fix: "आपके card पे payment due है." |
| "आधा अभी कर दीजिए." | VERIFIED | H3 block |
| "मैं समझ सकती हूँ, पर minimum आज कर दीजिए." | Negotiation | H5 block |
| "Let me check with the team." | Dispute | H6 block |
| "आपका MAD three thousand है." | — | H7 + H3 block |
| "Pay कर पाएंगे?" | — | Auto-fix `?` → `.` |
| "₹3500 pay कीजिए" | — | H4 block (digits) |
| "आप UPI से आज pay कर दीजिए." | account_block | H15 block |
