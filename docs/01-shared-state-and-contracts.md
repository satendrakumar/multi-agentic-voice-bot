# 01 — Shared State & Agent Contracts

## 1. `CallState` schema

One `CallState` object exists per call. **Only the Orchestrator writes to it**. Agents propose changes through `state_updates`, and the Orchestrator checks and applies them.

```python
from dataclasses import dataclass, field
from enum import Enum
from datetime import date

class IdentityStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"      # start state — lock closed
    VERIFIED = "VERIFIED"          # explicit self-identification
    DENIED = "DENIED"              # "नहीं" / not [NAME]
    WRONG_NUMBER = "WRONG_NUMBER"
    THIRD_PARTY = "THIRD_PARTY"    # knows [NAME]

class Lang(str, Enum):
    HINDI = "HINDI"                # Hinglish
    ENGLISH = "ENGLISH"

class ReasonClass(str, Enum):
    UNKNOWN = "unknown"
    FIRM_TODAY = "firm_today"
    WILLING = "willing"            # forgot / meant to pay
    HARDSHIP = "hardship"          # job/business loss, salary delay, money crunch
    STALLING = "stalling"          # shopping, travel, "next week", vague
    REFUSAL = "refusal"
    WRONG_AMOUNT = "wrong_amount"
    STATEMENT_NOT_RECEIVED = "statement_not_received"

class Stage(str, Enum):
    IDENTITY = "IDENTITY"
    DISCLOSURE = "DISCLOSURE"
    REASON = "REASON"
    NEGOTIATION = "NEGOTIATION"
    DISPUTE = "DISPUTE"
    SERVICING = "SERVICING"
    SAFETY = "SAFETY"
    CLOSING = "CLOSING"
    END = "END"

ImpactAngle = str   # "cibil" | "card_block" | "future_credit" | "escalation" | "other_products"
FundsIdea = str     # "savings_family" | "alt_mode" | "salary_anchor"

@dataclass
class Profile:                      # read-only, from the dialler / CRM
    name: str                       # {NAME}
    name_dev: str                   # [NAME] — Devanagari, produced by S1 at call start
    card_name: str                  # {CARD_NAME}
    card_last4: str                 # {CARD_LAST4}
    out: int | float                # {OUT}
    mad: int | float                # {MAD}
    due_date: date                  # {DUE_DATE}
    today: date                     # {user_time_day}

@dataclass
class Commitment:
    amount: str | None = None       # "OUT" | "MAD" — never a number
    ptp_date: date | None = None
    mode: str | None = None         # "upi" | "net_banking" | "payzapp" | "app" | "link" | "debit_note" ...
    firm_today: bool = False

@dataclass
class CallState:
    profile: Profile
    stage: Stage = Stage.IDENTITY
    prev_stage: Stage | None = None
    turn_no: int = 0                            # bot turns spoken

    # identity
    identity_status: IdentityStatus = IdentityStatus.UNVERIFIED
    identity_reasks: int = 0

    # language (S1)
    language: Lang = Lang.HINDI
    language_locked: bool = False
    caller_lang_history: list[Lang] = field(default_factory=list)

    # reason
    reason_class: ReasonClass = ReasonClass.UNKNOWN
    reason_text: str | None = None              # short paraphrase of caller's reason
    reason_asked: bool = False

    # negotiation
    ask_level: str = "OUT"                      # "OUT" -> "MAD" -> "DATE"
    out_spoken: bool = False                    # {OUT} value voiced (once, at open)
    mad_spoken: bool = False                    # {MAD} value voiced (once, first pivot)
    today_nudged: bool = False
    angles_used: list[ImpactAngle] = field(default_factory=list)
    angle_deepened: list[ImpactAngle] = field(default_factory=list)
    funds_ideas_used: list[FundsIdea] = field(default_factory=list)
    callouts: int = 0                           # stalling / shifting-excuse callouts
    hardship_asks: int = 0                      # max 2
    sub_mad_held: bool = False                  # "minimum is {MAD}" held once
    ptp_history: list[date] = field(default_factory=list)   # detect push-out vs pull-in
    commitment: Commitment = field(default_factory=Commitment)
    questions_asked: list[str] = field(default_factory=list) # normalised intents, to avoid repeats

    # levers / servicing
    levers_used: list[str] = field(default_factory=list)     # "settlement", "waiver", "emi", ...
    support_shared: bool = False
    support_confirmed: bool = False
    support_repeats: int = 0
    phone_update_asked: bool = False

    # safety / input
    abuse_warnings: int = 0
    injection_warnings: int = 0
    silence_count: int = 0
    bad_audio_retries: int = 0
    irritated: bool = False

    # closing
    help_asked: bool = False

    # transcript
    turns: list[dict] = field(default_factory=list)          # {"role","text","agent","lang"}
    summary: str = ""                                        # rolling handoff summary
```

### Invariants the Orchestrator enforces

| # | Invariant |
|---|---|
| I1 | `profile.card_*`, `out`, `mad` and `due_date` are **not included** in any agent context while `identity_status != VERIFIED` |
| I2 | `commitment.amount ∈ {None, "OUT", "MAD"}`, and no other amount can be stored |
| I3 | An angle already in `angles_used` cannot be chosen again; the Negotiation agent gets only the **remaining** angles |
| I4 | `mad_spoken` becomes true the first time the {MAD} value is voiced. After that the context tells the agent to say "the minimum" |
| I5 | `stage = END` is terminal; exactly one ENDCALL is emitted |
| I6 | `language_locked` becomes true after bot turn 3; only an explicit switch request can change `language` after that |
| I7 | `reason_class` is set once and changes only with `signals.reason_contradiction = true` |

## 2. Agent I/O contract

### 2.1 Input — `AgentContext` (built by the Orchestrator per turn)

```json
{
  "agent": "negotiation",
  "turn_no": 7,
  "language": "HINDI",
  "name_allowed_this_turn": false,
  "customer": {
    "name_dev": "राहुल",
    "card_name": "Millennia",
    "card_last4_words": "one two three four",
    "out_words": "seventy thousand rupees",
    "mad_words": "three thousand five hundred rupees",
    "due_date_words": "fifteenth September",
    "today": "2026-09-29"
  },
  "state": {
    "reason_class": "stalling",
    "reason_text": "went on a trip, will pay next week",
    "ask_level": "MAD",
    "mad_spoken": true,
    "today_nudged": true,
    "angles_remaining": ["card_block", "future_credit", "escalation", "other_products"],
    "angles_used": ["cibil"],
    "funds_ideas_remaining": ["alt_mode", "salary_anchor"],
    "callouts": 1,
    "commitment": {"amount": "MAD", "ptp_date": null, "mode": null},
    "ptp_history": [],
    "questions_asked": ["can_pay_today", "reason", "mad_today"]
  },
  "summary": "Verified. Caller says pending due to travel, promised next week. Called out once, cibil angle used.",
  "recent_turns": [ {"role": "bot", "text": "..."}, {"role": "user", "text": "..."} ],
  "user_utterance": "अरे अगले हफ्ते पक्का कर दूँगा"
}
```

Rules:
- `customer.*` values are **already converted to spoken words** by S1/S2 helpers, so agents never do number conversion.
- `customer` holds only `name_dev` while UNVERIFIED (invariant I1).
- `recent_turns` = last 6 turns. Older context goes in `summary`.
- `name_allowed_this_turn` is true only on bot turns 1–2 and on the turn where `end_call` is expected.

### 2.2 Output — `AgentResult` (every LLM agent, JSON, `speech` first)

```json
{
  "speech": "देखिए, due fifteenth से pending है, next week तक रुकना ठीक नहीं, आज या कल minimum कर दीजिए.",
  "signals": {
    "topic": null,
    "hardstop": null,
    "identity": null,
    "reason_class": null,
    "reason_contradiction": false,
    "commitment": {"amount": "MAD", "ptp_date": null, "mode": null, "firm_today": false},
    "angle_used": null,
    "funds_idea_used": null,
    "callout": true,
    "irritated": false,
    "language_switch_request": null,
    "question_intent": "binary_date"
  },
  "state_updates": {},
  "handoff": null,
  "end_call": false
}
```

| Field | Meaning |
|---|---|
| `speech` | The utterance with no language tag and no ENDCALL. S1 adds the tag; the Orchestrator adds ENDCALL |
| `signals.topic` | A detected side topic that needs another agent (`wrong_amount`, `settlement`, `already_paid`, …) |
| `signals.hardstop` | The agent's own backup detection of a hard-stop (the classifier is primary) |
| `signals.question_intent` | Normalised intent of the question asked this turn. Used to block repeats |
| `handoff` | `null` (stay) or the target agent name. The Orchestrator checks it against the routing table |
| `end_call` | Ask the Orchestrator to end after this speech |

### 2.3 Hard-stop classifier contract

```json
// input
{"utterance": "papa hospital में हैं, surgery चल रही है", "stage": "NEGOTIATION"}
// output
{"hardstop": "distress", "confidence": 0.93}
// hardstop ∈ null | distress | self_harm | deceased | abuse | opt_out | injection | voicemail
```

Pre-emption threshold: `confidence ≥ 0.6` for distress, self_harm and deceased (these favour recall); `≥ 0.8` for the others.

## 3. Handoff rules

1. **Handoffs happen only through the Orchestrator.** Agents never call each other.
2. **One chained hop per turn at most.** Example: the caller says "settlement करवा दो" during Negotiation. The Negotiation agent returns `topic=settlement, handoff=dispute` with an **empty** speech, and the Orchestrator calls the Dispute agent in the same turn. The Dispute agent's speech is spoken. If Dispute then pivots back (`handoff=negotiation`), the pivot line is part of Dispute's speech, and Negotiation takes over from the **next** caller turn.
3. **Context passes as a summary.** After each turn the Orchestrator updates the one-sentence `summary` (template-built from state; an LLM summary is optional). Incoming agents get `summary` + `recent_turns` and never the full transcript.
4. **Speech continuity.** The incoming agent must not re-introduce Sania or re-state {OUT}. That is enforced through `out_spoken`, `mad_spoken` and `questions_asked`.
5. **Return path.** DISPUTE and SERVICING save `prev_stage` and return to it (normally NEGOTIATION) unless they end the call.

## 4. Error handling

| Failure | Fallback |
|---|---|
| Agent returns invalid JSON | Retry once with a "return valid JSON" nudge; if it fails again, use a safe stage line from the fallback bank (per agent, per language) |
| S2 hard violation (leak, third amount, placeholder) | Regenerate once, adding the violation as feedback; if it fails again, use the fallback line |
| LLM timeout > 1.5 s | Speak a filler from the bank ("जी…") only if the stage allows it; otherwise the fallback line |
| Unknown handoff target | Ignore it and stay in the current stage |
